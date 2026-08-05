# -*- coding: utf-8 -*-
"""Scenario private refs must match scenario user_id (8_4 P1/P2)."""
from __future__ import annotations

import json
from pathlib import Path

import evaluation.check_scenario_user_consistency as scn


def test_shipped_scenarios_user_consistent() -> None:
    errs = scn.check()
    assert errs == [], errs


def test_detects_cross_user_private_ref(monkeypatch, tmp_path: Path) -> None:
    ds = tmp_path / "dataset"
    ds.mkdir()
    # preference belongs to user A
    (ds / "preference.jsonl").write_text(
        json.dumps(
            {
                "case_id": "PREF-X",
                "user_id": "usr_A",
                "split": "dev",
                "expected": {"preferences": []},
                "input_events": [],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    for name in (
        "conflict.jsonl",
        "forget.jsonl",
        "retrieval_queries.jsonl",
        "security.jsonl",
        "knowledge_corpus.jsonl",
    ):
        (ds / name).write_text("", encoding="utf-8")

    scenarios = [
        {
            "scenario_id": "SCN-T",
            "user_id": "usr_B",
            "ref_private_cases": ["PREF-X"],
            "ref_public_memory_ids": [],
        }
    ]
    sj = tmp_path / "scenarios.json"
    sj.write_text(json.dumps(scenarios), encoding="utf-8")

    monkeypatch.setattr(scn, "DATASET", ds)
    monkeypatch.setattr(scn, "SCENARIOS_JSON", sj)

    errs = scn.check()
    assert errs, "expected cross-user failure"
    assert any("PREF-X" in e and "usr_A" in e for e in errs)
