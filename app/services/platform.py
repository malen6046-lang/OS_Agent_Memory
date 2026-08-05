from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.repositories.protocols import PlatformRepository
from app.orchestrator import MemoryOrchestrator
from contracts.schemas import (
    CONTRACT_VERSION,
    ConflictResolveRequest,
    ConflictResult,
    EvaluationResult,
    EvaluationRunRequest,
    EvaluationStatus,
    EventIngestItem,
    EventIngestResult,
    ForgetExecuteRequest,
    ForgetFailedItem,
    ForgetPlan,
    ForgetPreviewRequest,
    ForgetResult,
    HealthResponse,
    HealthStatus,
    ItemOutcome,
    KnowledgeIngestItem,
    KnowledgeIngestRequest,
    KnowledgeIngestResult,
    KnowledgeMemoryResponse,
    MemoryKind,
    MemoryResponse,
    MemoryStatus,
    MemorySubtype,
    OperationStatus,
    PreferenceExtractResult,
    PreferenceListResult,
    PromotionResult,
    PromotionRunRequest,
    Provider,
    ProviderHealth,
    RiskLevel,
    SearchRequest,
    SearchResult,
    SearchResponse,
    ErrorCode,
)


class MemoryApiService:
    """V1.2.1 API facade over orchestrated algorithms and repositories."""

    def __init__(
        self,
        repository: PlatformRepository,
        *,
        orchestrator: MemoryOrchestrator | None = None,
        service_container: object | None = None,
    ) -> None:
        self._repository = repository
        self._orchestrator = orchestrator
        self._service_container = service_container

    async def ingest_events(self, events) -> EventIngestResult:
        await self._repository.save_events(events)
        return EventIngestResult(
            status=OperationStatus.ACCEPTED,
            task_id=None,
            items=[
                EventIngestItem(
                    source_event_id=event.source_event_id,
                    outcome=ItemOutcome.CREATED,
                    memory_ids=[f"mem_{uuid4()}"],
                )
                for event in events
            ],
        )

    async def extract_preferences(self, events) -> PreferenceExtractResult:
        return PreferenceExtractResult(candidates=[])

    async def get_preferences(
        self, user_id: str, scene: str, keys: list[str] | None
    ) -> PreferenceListResult:
        items = await self._repository.list_preferences(user_id, scene, keys)
        return PreferenceListResult(items=items)

    async def preference_history(
        self, user_id: str, key: str
    ) -> PreferenceListResult:
        items = await self._repository.preference_versions(user_id, key)
        return PreferenceListResult(items=items)

    async def ingest_knowledge(
        self, request: KnowledgeIngestRequest
    ) -> KnowledgeIngestResult:
        algorithm_items: list[dict] = []
        if self._orchestrator is not None:
            result = await self._orchestrator.ingest_knowledge(request)
            if isinstance(result, dict):
                algorithm_items = result.get("items", [])

        items: list[KnowledgeIngestItem] = []
        for index, record in enumerate(request.records):
            algorithm_item = (
                algorithm_items[index] if index < len(algorithm_items) else {}
            )
            action = algorithm_item.get("status", "inserted")
            outcome = {
                "duplicate": ItemOutcome.DUPLICATE,
                "conflict": ItemOutcome.CONFLICT_PENDING,
                "inserted": ItemOutcome.CREATED,
            }.get(action, ItemOutcome.FAILED)
            memory = KnowledgeMemoryResponse(
                memory_id=algorithm_item.get("memory_id", f"mem_{uuid4()}"),
                user_id=request.user_id,
                memory_kind=MemoryKind.SEMANTIC,
                subtype=MemorySubtype.FACT,
                content_text=record.body,
                content=record,
                status=MemoryStatus.ACTIVE,
                confidence=record.source_reliability,
                importance=record.source_reliability,
                revision=1,
                valid_from=record.effective_at,
                valid_to=None,
                expires_at=None,
                scene_tags=[],
                source_refs=[request.source_event_id],
                supersedes=[],
                attributes={},
            )
            items.append(
                KnowledgeIngestItem(
                    input_index=index,
                    outcome=outcome,
                    memory=memory,
                )
            )
        status = (
            OperationStatus.ACCEPTED
            if all(item.outcome is not ItemOutcome.FAILED for item in items)
            else OperationStatus.PARTIAL_FAILURE
        )
        response = KnowledgeIngestResult(status=status, items=items)
        await self._repository.save_knowledge(request, response)
        return response

    async def get_memory(
        self, user_id: str, memory_id: str
    ) -> MemoryResponse | None:
        return await self._repository.get_memory(user_id, memory_id)

    async def memory_transitions(
        self, user_id: str, memory_id: str | None = None
    ) -> list[dict]:
        return await self._repository.list_transitions(user_id, memory_id)

    async def search(self, request: SearchRequest) -> SearchResponse:
        if self._orchestrator is None:
            return SearchResponse(items=[])
        result = await self._orchestrator.search_memory(request)
        raw_items = result.get("items", []) if isinstance(result, dict) else []
        items: list[SearchResult] = []
        now = datetime.now(timezone.utc)
        for rank, item in enumerate(raw_items, start=1):
            metadata = item.get("metadata", {})
            valid_from = metadata.get("valid_from") or now
            source_refs = [ref for ref in metadata.get("source_refs", []) if ref]
            memory = MemoryResponse(
                memory_id=item["memory_id"],
                user_id=request.user_id,
                memory_kind=metadata.get("memory_kind", item.get("memory_kind", "semantic")),
                subtype=metadata.get("subtype", "fact"),
                content_text=item.get("content_text", metadata.get("content_text", "")),
                content=metadata.get("content", {}),
                status=metadata.get("status", "active"),
                confidence=metadata.get("confidence", 0.8),
                importance=metadata.get("importance", 0.8),
                revision=metadata.get("revision", 1),
                valid_from=valid_from,
                valid_to=None,
                expires_at=None,
                scene_tags=[metadata["scene"]] if metadata.get("scene") else [],
                source_refs=source_refs,
                supersedes=[],
                attributes={},
            )
            items.append(
                SearchResult(memory=memory, rank=rank, score=item.get("score", 0.0))
            )
        return SearchResponse(items=items)

    async def resolve_conflict(
        self, conflict_id: str, request: ConflictResolveRequest
    ) -> ConflictResult:
        return ConflictResult(
            conflict_id=conflict_id,
            decision=request.decision,
            memory=None,
        )

    async def preview_forget(self, request: ForgetPreviewRequest) -> ForgetPlan:
        return ForgetPlan(
            plan_id=f"plan_{uuid4()}",
            candidates=[],
            risk_level=RiskLevel.LOW,
            confirmation_token=f"confirm_{uuid4()}",
        )

    async def execute_forget(
        self, request: ForgetExecuteRequest
    ) -> ForgetResult:
        return ForgetResult(
            plan_id=f"plan_{uuid4()}",
            requested_ids=request.selected_ids,
            tombstoned_ids=[],
            failed_items=[
                ForgetFailedItem(
                    memory_id=memory_id,
                    code=ErrorCode.STORAGE_WRITE_FAILED,
                    message="Mock Service未执行真实删除",
                )
                for memory_id in request.selected_ids
            ],
            audit_id=f"audit_{uuid4()}",
        )

    async def run_promotions(
        self, request: PromotionRunRequest
    ) -> PromotionResult:
        return PromotionResult(
            promoted_count=0,
            promoted_ids=[],
            degraded_count=0,
            degraded_ids=[],
            expired_count=0,
            expired_ids=[],
        )

    async def health(self) -> HealthResponse:
        return HealthResponse(
            status=HealthStatus.DEGRADED,
            service_version="0.1.0",
            contract_version=CONTRACT_VERSION,
            components={
                "api": ProviderHealth(
                    status=HealthStatus.OK,
                    provider=Provider.DETERMINISTIC_TEST,
                    message="FastAPI骨架可用",
                ),
                "repository": ProviderHealth(
                    status=HealthStatus.DEGRADED,
                    provider=Provider.DETERMINISTIC_TEST,
                    message="当前使用内存Mock Repository",
                ),
                "embedding": ProviderHealth(
                    status=HealthStatus.NOT_CONFIGURED,
                    provider=Provider.DETERMINISTIC_TEST,
                    message="尚未接入真实Embedding Provider",
                ),
                "vector_store": ProviderHealth(
                    status=HealthStatus.NOT_CONFIGURED,
                    provider=Provider.DETERMINISTIC_TEST,
                    message="尚未接入真实VectorStore Adapter",
                ),
            },
            model_info=None,
            index_info=None,
        )

    async def run_evaluation(
        self, request: EvaluationRunRequest
    ) -> EvaluationResult:
        result = EvaluationResult(
            evaluation_run_id=f"eval_{uuid4()}",
            status=EvaluationStatus.ACCEPTED,
            evaluation_types=request.evaluation_types,
            created_at=datetime.now(timezone.utc),
            started_at=None,
            completed_at=None,
            report_uri=None,
            metrics=None,
            error=None,
        )
        await self._repository.create_evaluation(request, result)
        return result
