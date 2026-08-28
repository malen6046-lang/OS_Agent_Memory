#!/usr/bin/env python3
"""Evaluate the real preference/conflict adapters on Dataset V0.1.

Held-out data is deliberately guarded so normal development runs cannot leak it
into rule tuning.  The report includes per-case predictions and error labels in
addition to the competition-facing aggregate metrics.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from adapters.knowledge_retrieval.knowledge import KnowledgeServiceAdapter
from adapters.preference_safety.preference import PreferenceServiceAdapter
from contracts.schemas.envelope import Envelope
from contracts.schemas.memory import MemoryRecord
from evaluation.loaders import load_cases
from evaluation.metrics import (
    PREF_MATCH_FIELDS,
    multilabel_prf,
    preference_set_exact_match,
    preference_signature,
)


RELATIONS = (
    "duplicate",
    "support",
    "extend",
    "replace",
    "contradict",
    "unrelated",
)


class _UnusedEmbedding:
    def health(self, deep: bool = False) -> dict[str, Any]:
        del deep
        return {"provider": "evaluation", "status": "ok", "details": {}}

    def model_info(self) -> dict[str, Any]:
        return {
            "provider": "evaluation",
            "model_name": "unused",
            "dimension": 1,
        }

    def encode(self, texts: list[str]) -> dict[str, Any]:
        return {
            "vectors": [[0.0] for _ in texts],
            "model_name": "unused",
            "dimension": 1,
        }


class _UnusedVectorStore:
    def query(self, request: Any) -> list[Any]:
        del request
        return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--split",
        default="dev",
        choices=("dev", "held_out"),
    )
    parser.add_argument(
        "--allow-held-out",
        action="store_true",
        help="required for the one-time frozen held-out run",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "evaluation/reports/preference_conflict_current_dev.json"
        ),
    )
    args = parser.parse_args()
    if args.split == "held_out" and not args.allow_held_out:
        parser.error(
            "held_out is sealed during tuning; pass --allow-held-out only "
            "after the algorithm is frozen"
        )

    report = {
        "status": "ok",
        "split": args.split,
        "preference": evaluate_preference(args.split),
        "conflict": evaluate_conflict(args.split),
    }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(_summary(report), ensure_ascii=False, indent=2))
    print(f"report written: {output}")
    return 0


def evaluate_preference(split: str) -> dict[str, Any]:
    service = PreferenceServiceAdapter()
    case_results: list[dict[str, Any]] = []
    y_true: list[set[tuple[Any, ...]]] = []
    y_pred: list[set[tuple[Any, ...]]] = []
    exact_hits = 0
    ephemeral_count = 0
    ephemeral_false_positives = 0
    error_counts: Counter[str] = Counter()

    for case in load_cases("preference", split=split):
        gold = case.get("expected", {}).get("preferences", [])
        predictions = [
            _preference_prediction(candidate.model_dump(mode="json"))
            for candidate in service.extract(
                [Envelope.model_validate(event) for event in case["input_events"]]
            )
        ]
        exact = preference_set_exact_match(predictions, gold)
        exact_hits += int(exact)
        gold_signatures = {preference_signature(item) for item in gold}
        predicted_signatures = {
            preference_signature(item) for item in predictions
        }
        y_true.append(gold_signatures)
        y_pred.append(predicted_signatures)
        errors = _preference_errors(gold, predictions)
        error_counts.update(errors)

        is_ephemeral = bool(
            case.get("expected", {}).get("is_ephemeral_instruction")
        )
        if is_ephemeral:
            ephemeral_count += 1
            if predictions:
                ephemeral_false_positives += 1
        case_results.append(
            {
                "case_id": case["case_id"],
                "exact_match": exact,
                "is_ephemeral_instruction": is_ephemeral,
                "gold": gold,
                "predicted": predictions,
                "errors": errors,
            }
        )

    count = len(case_results)
    metrics = multilabel_prf(y_true, y_pred)
    return {
        "case_count": count,
        "exact_match_accuracy": _ratio(exact_hits, count),
        **{key: round(value, 6) for key, value in metrics.items()},
        "ephemeral": {
            "case_count": ephemeral_count,
            "false_positive_count": ephemeral_false_positives,
            "false_positive_rate": _ratio(
                ephemeral_false_positives,
                ephemeral_count,
            ),
        },
        "match_fields": list(PREF_MATCH_FIELDS),
        "error_counts": dict(sorted(error_counts.items())),
        "case_results": case_results,
    }


def evaluate_conflict(split: str) -> dict[str, Any]:
    service = KnowledgeServiceAdapter(
        _UnusedEmbedding(),
        _UnusedVectorStore(),
    )
    case_results: list[dict[str, Any]] = []
    relation_hits = 0
    strategy_hits = 0
    joint_hits = 0
    predicted_manual_review = 0
    gold_manual_review = 0
    confusion: Counter[tuple[str, str]] = Counter()

    for case in load_cases("conflict", split=split):
        decision = service.classify_conflict(
            MemoryRecord.model_validate(case["old"]),
            MemoryRecord.model_validate(case["new"]),
        ).model_dump(mode="json")
        expected = case["expected"]
        predicted_relation = decision["relation"]
        predicted_strategy = decision["strategy"]
        expected_relation = expected["relation"]
        expected_strategy = expected["strategy"]
        relation_match = predicted_relation == expected_relation
        strategy_match = predicted_strategy == expected_strategy
        joint_match = relation_match and strategy_match
        relation_hits += int(relation_match)
        strategy_hits += int(strategy_match)
        joint_hits += int(joint_match)
        predicted_manual_review += int(
            predicted_strategy == "manual_review"
        )
        gold_manual_review += int(expected_strategy == "manual_review")
        confusion[(expected_relation, predicted_relation)] += 1
        errors = []
        if not relation_match:
            errors.append("relation")
        if not strategy_match:
            errors.append("strategy")
        case_results.append(
            {
                "case_id": case["case_id"],
                "joint_match": joint_match,
                "old": case["old"],
                "new": case["new"],
                "gold": expected,
                "predicted": decision,
                "errors": errors,
            }
        )

    count = len(case_results)
    matrix = {
        expected: {
            predicted: confusion[(expected, predicted)]
            for predicted in RELATIONS
        }
        for expected in RELATIONS
    }
    return {
        "case_count": count,
        "primary_metric": "joint_accuracy",
        "joint_accuracy": _ratio(joint_hits, count),
        "relation_accuracy": _ratio(relation_hits, count),
        "strategy_accuracy": _ratio(strategy_hits, count),
        "predicted_manual_review_rate": _ratio(
            predicted_manual_review,
            count,
        ),
        "gold_manual_review_rate": _ratio(gold_manual_review, count),
        "auto_apply_rate": _ratio(count - predicted_manual_review, count),
        "confusion_matrix_relation": matrix,
        "case_results": case_results,
    }


def _preference_prediction(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "preference_key": candidate["preference_key"],
        "value": candidate["value"],
        "category": candidate["category"],
        "scope": candidate["scope"],
        "scope_value": candidate["scope_value"],
        "polarity": candidate["polarity"],
        "status": "active",
    }


def _preference_errors(
    gold: list[dict[str, Any]],
    predicted: list[dict[str, Any]],
) -> list[str]:
    if not gold and predicted:
        return ["ephemeral_false_positive"]
    if gold and not predicted:
        return ["missing"]
    errors: set[str] = set()
    gold_by_key = _group_by_key(gold)
    predicted_by_key = _group_by_key(predicted)
    if set(gold_by_key) - set(predicted_by_key):
        errors.add("missing_key")
    if set(predicted_by_key) - set(gold_by_key):
        errors.add("extra_key")
    for key in set(gold_by_key) & set(predicted_by_key):
        gold_items = gold_by_key[key]
        predicted_items = predicted_by_key[key]
        if len(predicted_items) > len(gold_items):
            errors.add("extra")
        for expected, actual in zip(gold_items, predicted_items):
            for field in PREF_MATCH_FIELDS[1:]:
                if expected.get(field) != actual.get(field):
                    errors.add(field)
    return sorted(errors)


def _group_by_key(
    preferences: Iterable[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for preference in preferences:
        grouped.setdefault(str(preference.get("preference_key")), []).append(
            preference
        )
    return grouped


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    preference = report["preference"]
    conflict = report["conflict"]
    return {
        "status": report["status"],
        "split": report["split"],
        "preference": {
            "case_count": preference["case_count"],
            "exact_match_accuracy": preference["exact_match_accuracy"],
            "micro_f1": preference["micro_f1"],
            "macro_f1": preference["macro_f1"],
            "ephemeral_false_positive_rate": preference["ephemeral"][
                "false_positive_rate"
            ],
            "error_counts": preference["error_counts"],
        },
        "conflict": {
            "case_count": conflict["case_count"],
            "joint_accuracy": conflict["joint_accuracy"],
            "relation_accuracy": conflict["relation_accuracy"],
            "strategy_accuracy": conflict["strategy_accuracy"],
            "predicted_manual_review_rate": conflict[
                "predicted_manual_review_rate"
            ],
            "auto_apply_rate": conflict["auto_apply_rate"],
        },
    }


if __name__ == "__main__":
    raise SystemExit(main())
