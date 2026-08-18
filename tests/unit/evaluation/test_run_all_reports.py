# -*- coding: utf-8 -*-
"""run_all report writers: Markdown, CSV, TXT snapshot (no absolute paths)."""
from __future__ import annotations

import csv
import re
from pathlib import Path
from pprint import pformat

from evaluation.run_all import write_evaluation_report_md, write_result_csv


def _summary() -> dict:
    return {
        "started_at": "2026-08-05T00:00:00+00:00",
        "split": "dev",
        "runtime": {
            "python_version": "3.12.7",
            "requires": "CPython >=3.12,<3.13",
            "executable": "python3.12",
        },
        "tasks": {
            "preference": {
                "n": 2,
                "exact_match_accuracy": 0.5,
                "micro_f1": 0.4,
                "macro_f1": 0.3,
                "ephemeral_false_positive_rate": 0.0,
                "status": "baseline_not_competition_claim",
            },
            "retrieval": {
                "n": 3,
                "recall_at_k": {"1": 0.1, "3": 0.2, "5": 0.3, "10": 0.4},
                "mrr": 0.25,
                "latency_ms": {"p95": 4.0},
                "status": "baseline_not_competition_claim",
            },
            "conflict": {
                "n": 1,
                "joint_accuracy": 0.1,
                "relation_accuracy": 0.2,
                "strategy_accuracy": 0.3,
                "auto_apply_rate": 0.9,
                "predicted_manual_review_rate": 0.1,
                "status": "baseline_not_competition_claim",
            },
            "forget": {
                "n": 1,
                "preview_precision": 0.5,
                "preview_recall": 0.6,
                "execute_success_rate": 0.4,
                "false_delete_count": 0,
                "status": "baseline_not_competition_claim",
            },
            "security": {
                "n": 1,
                "block_accuracy": 0.9,
                "entity_type_accuracy": 0.8,
                "joint_accuracy": 0.8,
                "status": "baseline_not_competition_claim",
            },
            "latency": {
                "n": 3,
                "p50_ms": 1.0,
                "p95_ms": 4.0,
                "mean_ms": 2.0,
                "status": "baseline_not_competition_claim",
            },
        },
    }


def test_write_markdown_csv_txt(tmp_path: Path) -> None:
    summary = _summary()
    md = tmp_path / "evaluation_report.md"
    csv_path = tmp_path / "result.csv"
    txt = tmp_path / "v0.1_dev.txt"

    write_evaluation_report_md(md, summary)
    write_result_csv(csv_path, summary)
    txt.write_text(pformat(summary, width=100, sort_dicts=False), encoding="utf-8")

    md_text = md.read_text(encoding="utf-8")
    assert "python_version=3.12.7" in md_text
    assert "python3.12" in md_text
    assert "baseline_not_competition_claim" in md_text
    assert not re.search(r"[A-Za-z]:\\\\|/home/|/Users/", md_text)
    assert "anaconda" not in md_text.lower()

    with csv_path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows
    metrics = {(r["task"], r["metric"]) for r in rows}
    assert ("preference", "exact_match_accuracy") in metrics
    assert ("retrieval", "recall_at_k.5") in metrics
    assert ("security", "entity_type_accuracy") in metrics
    assert all(r["split"] == "dev" for r in rows)

    assert txt.exists() and "python3.12" in txt.read_text(encoding="utf-8")
