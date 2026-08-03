# -*- coding: utf-8 -*-
"""Conflict eval — data from evaluation/dataset/conflict.jsonl."""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from pprint import pprint
from typing import Any, Callable

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from evaluation.loaders import load_cases
from modules.knowledge_retrieval.knowledge_service import KnowledgeService

RELATIONS = ("duplicate", "support", "extend", "replace", "contradict", "unrelated")
STRATEGIES = ("keep_old", "keep_new", "merge", "manual_review")


class _NullEmb:
    def health(self, deep: bool = False) -> dict:
        return {"status": "stopped"}

    def encode(self, texts: list[str]) -> dict:
        return {"vectors": [], "dimension": 0, "errors": None}


class _NullVS:
    def query(self, request: dict) -> list:
        return []


def run_conflict_eval(
    *,
    split: str = "dev",
    classify_fn: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    cases = load_cases("conflict", split=split)
    fn = classify_fn or KnowledgeService(_NullEmb(), _NullVS(), bm25=None).classify_conflict
    rel_ok = strat_ok = joint_ok = 0
    pred_manual = gold_manual = 0
    confusion = Counter()
    for case in cases:
        pred = fn(case["old"], case["new"])
        exp = case["expected"]
        pr, er = pred.get("relation"), exp.get("relation")
        ps, es = pred.get("strategy"), exp.get("strategy")
        confusion[(er, pr)] += 1
        r_hit, s_hit = pr == er, ps == es
        rel_ok += int(r_hit)
        strat_ok += int(s_hit)
        joint_ok += int(r_hit and s_hit)
        pred_manual += int(ps == "manual_review")
        gold_manual += int(es == "manual_review")
    n = max(len(cases), 1)
    # full 6x6 relation confusion skeleton
    matrix = {f"{a}->{b}": confusion.get((a, b), 0) for a in RELATIONS for b in RELATIONS}
    return {
        "task": "conflict",
        "split": split,
        "n": len(cases),
        "primary_metric": "joint_accuracy",
        "joint_accuracy": joint_ok / n,
        "relation_accuracy": rel_ok / n,
        "strategy_accuracy": strat_ok / n,
        "predicted_manual_review_rate": pred_manual / n,
        "gold_manual_review_rate": gold_manual / n,
        "auto_apply_rate": 1.0 - (pred_manual / n),
        "confusion_matrix_relation": matrix,
        "classifier": "KnowledgeService.classify_conflict",
        "status": "baseline_not_competition_claim",
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--split", default="dev", choices=["dev", "held_out", "all"])
    args = p.parse_args()
    pprint(run_conflict_eval(split=args.split))


if __name__ == "__main__":
    main()
