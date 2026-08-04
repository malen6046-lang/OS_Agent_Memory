"""Evaluation service Protocol frozen by CR-20260803-001."""

from typing import Protocol

from contracts.schemas.evaluation import EvaluationRun, EvaluationRunRequest


class EvaluationService(Protocol):
    def run(self, request: EvaluationRunRequest) -> EvaluationRun: ...
