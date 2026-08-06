# -*- coding: utf-8 -*-
"""Adapter stubs for wiring real services into evaluation runners (8_4 P4).

4号只提供签名与包装；真实 PreferenceService / KnowledgeService / ForgetService /
SafetyService 由 1/2 号实现后在此接入。
"""
from __future__ import annotations

from typing import Any, Callable, Protocol


class PreferenceExtractor(Protocol):
    def extract_from_case(self, case: dict[str, Any]) -> list[dict[str, Any]]: ...


class KnowledgeSearcher(Protocol):
    def search_case(self, case: dict[str, Any]) -> dict[str, Any]: ...


class ConflictClassifier(Protocol):
    def classify(self, old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]: ...


class ForgetPreviewer(Protocol):
    def preview(self, case: dict[str, Any]) -> dict[str, Any]: ...


class SafetyDetector(Protocol):
    def detect(self, text: str) -> dict[str, Any]: ...


def wrap_preference_service(
    service: Any | None,
    *,
    method: str = "extract_preferences",
) -> Callable[[dict[str, Any]], list[dict[str, Any]]] | None:
    """Return extract_fn for run_preference_eval, or None to keep baseline."""
    if service is None:
        return None

    def extract_fn(case: dict[str, Any]) -> list[dict[str, Any]]:
        if hasattr(service, "extract_from_case"):
            return list(service.extract_from_case(case))
        fn = getattr(service, method)
        events = case.get("input_events") or []
        out = fn(events) if events else fn(case)
        if isinstance(out, dict) and "preferences" in out:
            return list(out["preferences"])
        return list(out)

    return extract_fn


def wrap_knowledge_search(
    service: Any | None,
    *,
    method: str = "search",
) -> Callable[[dict[str, Any]], dict[str, Any]] | None:
    """Return search_fn for run_retrieval_eval."""
    if service is None:
        return None

    def search_fn(case: dict[str, Any]) -> dict[str, Any]:
        if hasattr(service, "search_case"):
            return service.search_case(case)
        fn = getattr(service, method)
        resp = fn(
            {
                "query": case["query"],
                "user_id": case.get("user_id"),
                "top_k": 10,
            }
        )
        # Normalize common shapes
        if isinstance(resp, list):
            return {
                "results": [{"memory_id": x} if isinstance(x, str) else x for x in resp],
                "meta": {"elapsed_ms": 0.0},
            }
        return resp

    return search_fn


def wrap_conflict_classify(
    service: Any | None,
    *,
    method: str = "classify_conflict",
) -> Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None:
    if service is None:
        return None

    def classify_fn(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
        if hasattr(service, "classify"):
            return service.classify(old, new)
        return getattr(service, method)(old, new)

    return classify_fn


def wrap_forget_preview(
    service: Any | None,
    *,
    method: str = "preview_forget",
) -> Callable[[dict[str, Any]], dict[str, Any]] | None:
    if service is None:
        return None

    def preview_fn(case: dict[str, Any]) -> dict[str, Any]:
        if hasattr(service, "preview"):
            return service.preview(case)
        return getattr(service, method)(case)

    return preview_fn


def wrap_safety_detect(
    service: Any | None,
    *,
    method: str = "detect",
) -> Callable[[str], dict[str, Any]] | None:
    if service is None:
        return None

    def detect_fn(text: str) -> dict[str, Any]:
        if hasattr(service, "detect"):
            return service.detect(text)
        return getattr(service, method)(text)

    return detect_fn
