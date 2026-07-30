from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.repositories.protocols import MemoryRepository
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
    SearchResponse,
    ErrorCode,
)


class PlatformService:
    """V1.1契约Mock。只验证接口边界，不实现真实业务或持久化。"""

    def __init__(self, repository: MemoryRepository) -> None:
        self._repository = repository

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
        return PreferenceListResult(items=[])

    async def preference_history(
        self, user_id: str, key: str
    ) -> PreferenceListResult:
        return PreferenceListResult(items=[])

    async def ingest_knowledge(
        self, request: KnowledgeIngestRequest
    ) -> KnowledgeIngestResult:
        items: list[KnowledgeIngestItem] = []
        for index, record in enumerate(request.records):
            memory = KnowledgeMemoryResponse(
                memory_id=f"mem_{uuid4()}",
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
                    outcome=ItemOutcome.CREATED,
                    memory=memory,
                )
            )
        return KnowledgeIngestResult(status=OperationStatus.ACCEPTED, items=items)

    async def search(self, request: SearchRequest) -> SearchResponse:
        return SearchResponse(items=[])

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
        return EvaluationResult(
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
