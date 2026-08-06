# -*- coding: utf-8 -*-
"""Conflict eval: full 6-class relation confusion matrix."""
from __future__ import annotations

from evaluation.conflict_eval import RELATIONS, run_conflict_eval


def test_confusion_matrix_covers_all_six_relations(monkeypatch) -> None:
    # One gold per relation; classifier always predicts "unrelated".
    cases = []
    for i, rel in enumerate(RELATIONS):
        cases.append(
            {
                "case_id": f"CONF-T{i}",
                "old": {"content_text": "old", "user_id": "u"},
                "new": {"content_text": "new", "user_id": "u"},
                "expected": {"relation": rel, "strategy": "manual_review"},
            }
        )

    monkeypatch.setattr(
        "evaluation.conflict_eval.load_cases",
        lambda task, split="dev": cases,
    )

    def classify(_old, _new):
        return {"relation": "unrelated", "strategy": "manual_review"}

    report = run_conflict_eval(split="dev", classify_fn=classify)
    matrix = report["confusion_matrix_relation"]
    assert len(matrix) == 6 * 6
    for a in RELATIONS:
        for b in RELATIONS:
            key = f"{a}->{b}"
            assert key in matrix
            if b == "unrelated":
                assert matrix[key] == 1
            else:
                assert matrix[key] == 0
    assert report["n"] == 6
    assert report["relation_accuracy"] == 1 / 6  # only unrelated gold matches
    assert report["joint_accuracy"] == 1 / 6
    assert report["primary_metric"] == "joint_accuracy"
