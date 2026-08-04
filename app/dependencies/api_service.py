"""API-facing facade backed by the application-scoped orchestrator."""

from __future__ import annotations

from uuid import uuid4

from contracts.schemas.envelope import Envelope
from contracts.schemas.evaluation import EvaluationRunRequest as ContractEvaluationRunRequest
from contracts.schemas.forget import (
    ForgetExecuteRequest as ContractForgetExecuteRequest,
    ForgetPreviewRequest as ContractForgetPreviewRequest,
)
from contracts.schemas.retrieval import SearchRequest

from app.api.v1.schemas import (
    EvaluationRunRequest,
    ForgetExecuteRequest,
    ForgetPreviewRequest,
    MemorySearchRequest,
)
from app.orchestrator import MemoryOrchestrator

from .services import ServiceContainer
from .errors import OrchestratorResponseError


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
        result = await self._orchestrator.ingest(envelope)
        data = _orchestrator_data(result)
        return {
            "accepted": True,
            "source_event_id": envelope.source_event_id,
            "result": data,
            "mock": self._container.mode == "mock",
        }

    async def search_memory(
        self, request: MemorySearchRequest, request_id: str
    ) -> dict[str, object]:
        result = await self._orchestrator.search(
            SearchRequest(
                request_id=request_id,
                user_id=request.user_id,
                query=request.query,
                top_k=request.top_k,
                filters=request.filters,
            )
        )
        data = _orchestrator_data(result)
        return {
            "user_id": request.user_id,
            "query": request.query,
            "top_k": request.top_k,
            "items": data.get("items", []),
            "mock": self._container.mode == "mock",
        }

    async def preview_forget(
        self, request: ForgetPreviewRequest, request_id: str
    ) -> dict[str, object]:
        result = await self._orchestrator.preview_forget(
            ContractForgetPreviewRequest(
                request_id=request_id,
                user_id=request.user_id,
                memory_ids=request.memory_ids,
                reason=request.reason,
            )
        )
        data = _orchestrator_data(result)
        return {
            "plan_id": data.get("plan_id", f"forget_{uuid4().hex}"),
            "user_id": request.user_id,
            "affected_memory_ids": [
                candidate["memory_id"]
                for candidate in data.get("candidates", [])
            ],
            "confirmation_token": data.get("confirmation_token"),
            "requires_confirmation": data.get(
                "requires_confirmation", True
            ),
            "mock": self._container.mode == "mock",
        }

    async def execute_forget(
        self, request: ForgetExecuteRequest, request_id: str
    ) -> dict[str, object]:
        result = await self._orchestrator.execute_forget(
            ContractForgetExecuteRequest(
                request_id=request_id,
                user_id=request.user_id,
                plan_id=request.plan_id,
                confirmation_token=request.confirmation_token,
                selected_ids=request.selected_ids,
            )
        )
        data = _orchestrator_data(result)
        forget_result = data.get("forget_result", {})
        return {
            "plan_id": forget_result.get("plan_id", request.plan_id),
            "user_id": request.user_id,
            "status": "executed",
            "mock": self._container.mode == "mock",
        }

    async def run_evaluation(
        self, request: EvaluationRunRequest, request_id: str
    ) -> dict[str, object]:
        result = await self._orchestrator.run_evaluation(
            ContractEvaluationRunRequest(
                request_id=request_id,
                metric_names=request.metric_names,
                dataset=request.dataset,
            )
        )
        data = _orchestrator_data(result)
        data["mock"] = self._container.mode == "mock"
        return data


def _orchestrator_data(result: dict[str, object]) -> dict[str, object]:
    if result.get("success") is True:
        data = result.get("data")
        return data if isinstance(data, dict) else {"result": data}

    error = result.get("error")
    error = error if isinstance(error, dict) else {}
    raise OrchestratorResponseError(
        code=str(error.get("code", "INTERNAL_ERROR")),
        message=str(error.get("message", "Orchestrator failed")),
        retryable=bool(error.get("retryable", False)),
        details=error.get("details") if isinstance(error.get("details"), dict) else {},
    )
