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


class MockSafetyService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    async def check(self, request: Any) -> dict[str, Any]:
        self.calls.append(("check", request))
        return {"allowed": True, "mock": True}


class MockKnowledgeService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any, Any]] = []

    async def ingest(
        self, event: Any, preference_result: Any = None
    ) -> dict[str, Any]:
        self.calls.append(("ingest", event, preference_result))
        return {"records": [], "mock": True}


class MockRetriever:
    def __init__(
        self,
        embedding_provider: Any = None,
        vector_store: Any = None,
    ) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store

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


class MockEmbeddingProvider:
    """Deterministic lifecycle stub matching the V1.1 provider surface."""

    provider_name = "mock"

    def __init__(self, model_name: str = "default") -> None:
        self.model_name = model_name
        self.started = False
        self.closed = False
        self.lifecycle_events: list[str] = []

    def start(self) -> dict[str, Any]:
        self.lifecycle_events.append("embedding.start")
        self.started = True
        self.closed = False
        return self.health()

    def close(self) -> None:
        self.lifecycle_events.append("embedding.close")
        self.closed = True
        self.started = False

    def health(self, deep: bool = False) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "status": "ok" if self.started else "stopped",
            "deep": deep,
        }

    def model_info(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "model_name": self.model_name,
        }

    def encode(self, texts: list[str]) -> dict[str, Any]:
        return {
            "texts": list(texts),
            "vectors": [[] for _ in texts],
            "provider": self.provider_name,
        }


class FallbackEmbeddingProvider(MockEmbeddingProvider):
    provider_name = "fallback"


class MockVectorStoreAdapter:
    """In-memory lifecycle stub matching the V1.1 adapter surface."""

    provider_name = "mock"

    def __init__(self) -> None:
        self.started = False
        self.closed = False
        self.start_config: Any = None
        self.lifecycle_events: list[str] = []

    def start(self, config: Any) -> dict[str, Any]:
        self.lifecycle_events.append("vector.start")
        self.start_config = config
        self.started = True
        self.closed = False
        return self.health()

    def close(self) -> None:
        self.lifecycle_events.append("vector.close")
        self.closed = True
        self.started = False

    def health(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "status": "ok" if self.started else "stopped",
        }

    def ensure_collection(self, spec: Any) -> None:
        return None

    def upsert(self, items: list[Any]) -> dict[str, Any]:
        return {"upserted": len(items), "provider": self.provider_name}

    def query(self, request: Any) -> list[Any]:
        return []

    def delete(self, vector_pks: list[int]) -> dict[str, Any]:
        return {"deleted": len(vector_pks), "provider": self.provider_name}


class FallbackVectorStoreAdapter(MockVectorStoreAdapter):
    provider_name = "fallback"


def _request_value(request: Any, key: str, default: Any) -> Any:
    if isinstance(request, Mapping):
        return request.get(key, default)
    return getattr(request, key, default)
