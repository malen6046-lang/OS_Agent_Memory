"""Side-effect-free mock business service used by the API skeleton."""

from uuid import uuid4

from contracts.schemas.envelope import Envelope

from .v1.schemas import (
    EvaluationRunRequest,
    ForgetExecuteRequest,
    ForgetPreviewRequest,
    MemorySearchRequest,
)


class MockService:
    async def health(self) -> dict[str, object]:
        return {"status": "ok", "service": "os-agent-memory", "mock": True}

    async def ingest_event(self, envelope: Envelope) -> dict[str, object]:
        return {
            "accepted": True,
            "source_event_id": envelope.source_event_id,
            "mock": True,
        }

    async def search_memory(
        self, request: MemorySearchRequest, request_id: str | None = None
    ) -> dict[str, object]:
        return {
            "user_id": request.user_id,
            "query": request.query,
            "top_k": request.top_k,
            "items": [],
            "mock": True,
        }

    async def preview_forget(
        self, request: ForgetPreviewRequest, request_id: str | None = None
    ) -> dict[str, object]:
        return {
            "plan_id": f"forget_{uuid4().hex}",
            "user_id": request.user_id,
            "affected_memory_ids": request.memory_ids,
            "requires_confirmation": True,
            "mock": True,
        }

    async def execute_forget(
        self, request: ForgetExecuteRequest, request_id: str | None = None
    ) -> dict[str, object]:
        return {
            "plan_id": request.plan_id,
            "user_id": request.user_id,
            "status": "executed",
            "mock": True,
        }

    async def run_evaluation(
        self, request: EvaluationRunRequest, request_id: str | None = None
    ) -> dict[str, object]:
        return {
            "run_id": f"run_{uuid4().hex}",
            "status": "completed",
            "metrics": {name: 0.0 for name in request.metric_names},
            "mock": True,
        }
