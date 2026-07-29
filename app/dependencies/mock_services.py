"""Deterministic, side-effect-free service implementations for development."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class MockPreferenceService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    async def extract(self, event: Any) -> dict[str, Any]:
        self.calls.append(("extract", event))
        return {"preferences": [], "mock": True}


class MockKnowledgeService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any, Any]] = []

    async def ingest(
        self, event: Any, preference_result: Any
    ) -> dict[str, Any]:
        self.calls.append(("ingest", event, preference_result))
        return {"records": [], "mock": True}


class MockRetriever:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    async def search(self, request: Any) -> dict[str, Any]:
        self.calls.append(("search", request))
        return {"items": [], "mock": True}


class MockForgetService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    async def preview(self, request: Any) -> dict[str, Any]:
        self.calls.append(("preview", request))
        return {
            "plan_id": "forget_mock_plan",
            "memory_ids": _request_value(request, "memory_ids", []),
            "requires_confirmation": True,
            "mock": True,
        }

    async def execute(self, request: Any) -> dict[str, Any]:
        self.calls.append(("execute", request))
        return {
            "plan_id": _request_value(request, "plan_id", "forget_mock_plan"),
            "status": "executed",
            "mock": True,
        }


def _request_value(request: Any, key: str, default: Any) -> Any:
    if isinstance(request, Mapping):
        return request.get(key, default)
    return getattr(request, key, default)
