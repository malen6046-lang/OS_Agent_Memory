"""Evaluation adapters for the frozen V1.2.2 service contract."""

from .offline_service import OfflineEvaluationService, build_evaluation_service

__all__ = ["OfflineEvaluationService", "build_evaluation_service"]
