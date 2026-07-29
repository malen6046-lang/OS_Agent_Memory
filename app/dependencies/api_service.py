"""API-facing facade backed by the application-scoped orchestrator."""

from __future__ import annotations

from uuid import uuid4

from contracts.schemas.envelope import Envelope

from app.api.v1.schemas import (
    EvaluationRunRequest,
    ForgetExecuteRequest,
    ForgetPreviewRequest,
    MemorySearchRequest,
)
from app.orchestrator import MemoryOrchestrator

from .services import ServiceContainer


class OrchestratorApiService:
    """Keep routes independent of service construction and provider details."""

    def __init__(
        self,
        container: ServiceContainer,
        orchestrator: MemoryOrchestrator,
    ) -> None:
        self._container = container
        self._orchestrator = orchestrator

    async def health(self) -> dict[str, object]:
        embedding_health = self._container.embedding_provider.health()
        vector_health = self._container.vector_store.health()
        return {
            "status": "ok",
            "service": "os-agent-memory",
            "embedding": embedding_health,
            "vector_store": vector_health,
            "mock": self._container.mode == "mock",
        }

    async def ingest_event(self, envelope: Envelope) -> dict[str, object]:
        result = await self._orchestrator.ingest_event(envelope)
        return {
            "accepted": True,
            "source_event_id": envelope.source_event_id,
            "result": result,
            "mock": self._container.mode == "mock",
        }

    async def search_memory(
        self, request: MemorySearchRequest
    ) -> dict[str, object]:
        result = await self._orchestrator.search_memory(request)
        items = result.get("items", []) if isinstance(result, dict) else result
        return {
            "user_id": request.user_id,
            "query": request.query,
            "top_k": request.top_k,
            "items": items,
            "mock": self._container.mode == "mock",
        }

    async def preview_forget(
        self, request: ForgetPreviewRequest
    ) -> dict[str, object]:
        result = await self._orchestrator.preview_forget(request)
        result = result if isinstance(result, dict) else {}
        return {
            "plan_id": result.get("plan_id", f"forget_{uuid4().hex}"),
            "user_id": request.user_id,
            "affected_memory_ids": result.get(
                "memory_ids", request.memory_ids
            ),
            "requires_confirmation": result.get(
                "requires_confirmation", True
            ),
            "mock": self._container.mode == "mock",
        }

    async def execute_forget(
        self, request: ForgetExecuteRequest
    ) -> dict[str, object]:
        result = await self._orchestrator.execute_forget(request)
        result = result if isinstance(result, dict) else {}
        return {
            "plan_id": result.get("plan_id", request.plan_id),
            "user_id": request.user_id,
            "status": result.get("status", "executed"),
            "mock": self._container.mode == "mock",
        }

    async def run_evaluation(
        self, request: EvaluationRunRequest
    ) -> dict[str, object]:
        return {
            "run_id": f"run_{uuid4().hex}",
            "status": "completed",
            "metrics": {name: 0.0 for name in request.metric_names},
            "mock": self._container.mode == "mock",
        }
