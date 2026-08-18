"""Expose the repository's existing offline evaluators as EvaluationService.

This adapter does not change any evaluation algorithm.  It only translates the
frozen V1.2.2 request/response models to the runners under ``evaluation/``.
The underlying runners retain their ``baseline_not_competition_claim`` status.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from contracts.schemas.evaluation import EvaluationRun, EvaluationRunRequest
from evaluation.conflict_eval import run_conflict_eval
from evaluation.forget_eval import run_forget_eval
from evaluation.latency_eval import run_latency_eval
from evaluation.preference_eval import run_preference_eval
from evaluation.retrieval_eval import run_retrieval_eval
from evaluation.security_eval import run_security_eval


Runner = Callable[..., dict[str, Any]]

TASK_RUNNERS: dict[str, Runner] = {
    "preference": run_preference_eval,
    "retrieval": run_retrieval_eval,
    "conflict": run_conflict_eval,
    "forget": run_forget_eval,
    "security": run_security_eval,
    "latency": run_latency_eval,
}
VALID_SPLITS = {"dev", "held_out", "all"}


class OfflineEvaluationService:
    """Synchronous real implementation backed by the checked-in dataset."""

    provider_name = "offline_dataset_v0.1"

    def run(self, request: EvaluationRunRequest) -> EvaluationRun:
        split = str(request.dataset.get("split", "dev"))
        if split not in VALID_SPLITS:
            return self._result(request, status="failed", metrics={})

        task_names = self._task_names(request)
        reports: dict[str, dict[str, Any]] = {}
        try:
            for task_name in task_names:
                reports[task_name] = TASK_RUNNERS[task_name](split=split)
        except Exception:
            return self._result(request, status="failed", metrics={})

        available = _numeric_metrics(reports)
        selected = _select_metrics(request.metric_names, available)
        status = "completed" if len(selected) == len(request.metric_names) else "failed"
        return self._result(request, status=status, metrics=selected)

    @staticmethod
    def _task_names(request: EvaluationRunRequest) -> list[str]:
        configured = request.dataset.get("tasks")
        if isinstance(configured, list):
            selected = [str(item) for item in configured if str(item) in TASK_RUNNERS]
            if selected:
                return list(dict.fromkeys(selected))

        inferred = [
            metric.split(".", 1)[0]
            for metric in request.metric_names
            if metric.split(".", 1)[0] in TASK_RUNNERS
        ]
        return list(dict.fromkeys(inferred)) or list(TASK_RUNNERS)

    @staticmethod
    def _result(
        request: EvaluationRunRequest,
        *,
        status: str,
        metrics: dict[str, float],
    ) -> EvaluationRun:
        return EvaluationRun(
            run_id=f"run_{uuid4().hex}",
            request_id=request.request_id,
            status=status,
            metrics=metrics,
            created_at=datetime.now(timezone.utc),
        )


def build_evaluation_service() -> OfflineEvaluationService:
    """Factory used by the dependency container's configured loader."""

    return OfflineEvaluationService()


def _numeric_metrics(reports: Mapping[str, Any]) -> dict[str, float]:
    flattened: dict[str, float] = {}

    def walk(prefix: str, value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                walk(f"{prefix}.{key}" if prefix else str(key), item)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            flattened[prefix] = float(value)

    walk("", reports)
    return flattened


def _select_metrics(
    requested: list[str], available: Mapping[str, float]
) -> dict[str, float]:
    selected: dict[str, float] = {}
    for metric_name in requested:
        if metric_name in available:
            selected[metric_name] = available[metric_name]
            continue

        suffix = f".{metric_name}"
        matches = [value for key, value in available.items() if key.endswith(suffix)]
        if len(matches) == 1:
            selected[metric_name] = matches[0]
    return selected
