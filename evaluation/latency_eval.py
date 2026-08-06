# -*- coding: utf-8 -*-
"""Latency eval over retrieval dataset (DemoEmbedding ≠ Kylin evidence)."""
from __future__ import annotations

import argparse
from pprint import pprint
from typing import Any

from evaluation.retrieval_eval import run_retrieval_eval


def run_latency_eval(*, split: str = "dev") -> dict[str, Any]:
    report = run_retrieval_eval(split=split)
    lat = report["latency_ms"]
    return {
        "task": "latency",
        "split": split,
        "n": report["n"],
        "p50_ms": lat["p50"],
        "p95_ms": lat["p95"],
        "mean_ms": lat["mean"],
        "budget_ms": 500,
        "p95_within_budget_demo_only": lat["p95"] <= 500,
        "status": "baseline_not_competition_claim",
        "note": "Must re-measure on Kylin Real embedding/vector for ≤500ms claim",
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--split", default="dev", choices=["dev", "held_out", "all"])
    args = p.parse_args()
    pprint(run_latency_eval(split=args.split))


if __name__ == "__main__":
    main()
