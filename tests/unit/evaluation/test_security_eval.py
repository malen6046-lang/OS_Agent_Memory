# -*- coding: utf-8 -*-
"""Security eval: entity_type must match gold for joint hit."""
from __future__ import annotations

from evaluation.security_eval import baseline_detect, run_security_eval


def test_baseline_detect_entity_types() -> None:
    assert baseline_detect("密码是 secret123")["entity_type"] == "password"
    assert baseline_detect("token=sk-abc")["entity_type"] == "token"
    assert baseline_detect("记住我喜欢深色主题")["blocked_or_masked"] is False
    assert baseline_detect("记住我喜欢深色主题")["entity_type"] is None


def test_entity_type_accuracy_requires_match(monkeypatch) -> None:
    cases = [
        {
            "case_id": "SEC-T1",
            "input_text": "密码是 x",
            "expected": {
                "blocked_or_masked": True,
                "entity_type": "password",
                "error_code": "SENSITIVE_CONTENT_BLOCKED",
            },
        },
        {
            "case_id": "SEC-T2",
            "input_text": "token=sk-1",
            "expected": {
                "blocked_or_masked": True,
                "entity_type": "token",
                "error_code": "SENSITIVE_CONTENT_BLOCKED",
            },
        },
    ]
    monkeypatch.setattr(
        "evaluation.security_eval.load_cases",
        lambda task, split="dev": cases,
    )

    # Correct block+entity for both
    report_ok = run_security_eval(
        split="dev",
        detect_fn=lambda t: {
            "blocked_or_masked": True,
            "entity_type": "password" if "密码" in t else "token",
            "error_code": "SENSITIVE_CONTENT_BLOCKED",
        },
    )
    assert report_ok["block_accuracy"] == 1.0
    assert report_ok["entity_type_accuracy"] == 1.0
    assert report_ok["joint_accuracy"] == 1.0

    # Block ok but wrong entity_type → joint fails
    report_bad = run_security_eval(
        split="dev",
        detect_fn=lambda _t: {
            "blocked_or_masked": True,
            "entity_type": "phone",
            "error_code": "SENSITIVE_CONTENT_BLOCKED",
        },
    )
    assert report_bad["block_accuracy"] == 1.0
    assert report_bad["entity_type_accuracy"] == 0.0
