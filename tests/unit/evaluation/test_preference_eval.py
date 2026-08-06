# -*- coding: utf-8 -*-
"""Preference runner: exact-match + F1 wiring via inject extract_fn."""
from __future__ import annotations

from evaluation.preference_eval import run_preference_eval


def test_preference_eval_exact_and_f1(monkeypatch) -> None:
    cases = [
        {
            "case_id": "PREF-T1",
            "expected": {
                "preferences": [
                    {
                        "preference_key": "tool.editor",
                        "value": "kylin_ide",
                        "category": "tool_choice",
                        "scope": "global",
                        "scope_value": "global",
                        "polarity": "positive",
                        "status": "active",
                    }
                ],
                "is_ephemeral_instruction": False,
            },
            "input_events": [],
        },
        {
            "case_id": "PREF-T2",
            "expected": {"preferences": [], "is_ephemeral_instruction": True},
            "input_events": [],
        },
    ]
    monkeypatch.setattr(
        "evaluation.preference_eval.load_cases",
        lambda task, split="dev": cases,
    )

    gold = cases[0]["expected"]["preferences"]

    def extract(case):
        if case["case_id"] == "PREF-T1":
            return list(gold)
        return []

    report = run_preference_eval(split="dev", extract_fn=extract)
    assert report["n"] == 2
    assert report["exact_match_accuracy"] == 1.0
    assert report["ephemeral_false_positive_rate"] == 0.0
    assert report["micro_f1"] == 1.0
    assert report["macro_f1"] == 1.0
