from __future__ import annotations

from time import perf_counter
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.core.dependencies import get_api_service
from app.core.request_ids import validate_request_id
from app.core.responses import success
from app.services.platform import MemoryApiService
from contracts.schemas import (
    ConflictResolveRequest,
    ConflictResult,
    EvaluationResult,
    EvaluationRunRequest,
    EventIngestRequest,
    EventIngestResult,
    ForgetExecuteRequest,
    ForgetPlan,
    ForgetPreviewRequest,
    ForgetResult,
    HealthResponse,
    HealthQuery,
    KnowledgeIngestRequest,
    KnowledgeIngestResult,
    MemoryResponse,
    PreferenceExtractRequest,
    PreferenceExtractResult,
    PreferenceHistoryQuery,
    PreferenceListResult,
    PreferenceQuery,
    PromotionResult,
    PromotionRunRequest,
    Provider,
    SearchRequest,
    SearchResponse,
    SuccessResponse,
)

router = APIRouter()
Service = Annotated[MemoryApiService, Depends(get_api_service)]
RequestIdHeader = Annotated[str | None, Header(alias="X-Request-ID")]


@router.post("/events/ingest", response_model=SuccessResponse[EventIngestResult])
async def ingest_events(
    body: EventIngestRequest,
    service: Service,
    x_request_id: RequestIdHeader = None,
):
    started = perf_counter()
    request_id = validate_request_id(x_request_id, body.events[0].request_id)
    data = await service.ingest_events(body.events)
    return success(request_id=request_id, data=data, started_at=started)


@router.post(
    "/preferences/extract",
    response_model=SuccessResponse[PreferenceExtractResult],
)
async def extract_preferences(
    body: PreferenceExtractRequest,
    service: Service,
    x_request_id: RequestIdHeader = None,
):
    started = perf_counter()
    request_id = validate_request_id(x_request_id, body.events[0].request_id)
    data = await service.extract_preferences(body.events)
    return success(request_id=request_id, data=data, started_at=started)


@router.get("/preferences", response_model=SuccessResponse[PreferenceListResult])
async def get_preferences(
    query: Annotated[PreferenceQuery, Depends()],
    service: Service,
    x_request_id: RequestIdHeader = None,
):
    started = perf_counter()
    request_id = validate_request_id(x_request_id, query.request_id)
    data = await service.get_preferences(query.user_id, query.scene, query.keys)
    return success(request_id=request_id, data=data, started_at=started)


@router.get(
    "/preferences/{key}/history",
    response_model=SuccessResponse[PreferenceListResult],
)
@router.get(
    "/preferences/{key}/versions",
    response_model=SuccessResponse[PreferenceListResult],
)
async def preference_history(
    key: str,
    query: Annotated[PreferenceHistoryQuery, Depends()],
    service: Service,
    x_request_id: RequestIdHeader = None,
):
    started = perf_counter()
    request_id = validate_request_id(x_request_id, query.request_id)
    data = await service.preference_history(query.user_id, key)
    return success(request_id=request_id, data=data, started_at=started)


@router.post(
    "/knowledge/ingest",
    response_model=SuccessResponse[KnowledgeIngestResult],
)
@router.post(
    "/knowledge",
    response_model=SuccessResponse[KnowledgeIngestResult],
)
async def ingest_knowledge(
    body: KnowledgeIngestRequest,
    service: Service,
    x_request_id: RequestIdHeader = None,
):
    started = perf_counter()
    request_id = validate_request_id(x_request_id, body.request_id)
    data = await service.ingest_knowledge(body)
    return success(request_id=request_id, data=data, started_at=started)


@router.post(
    "/knowledge/conflicts/resolve",
    response_model=SuccessResponse[ConflictResult],
)
async def resolve_knowledge_conflict(
    body: ConflictResolveRequest,
    service: Service,
    conflict_id: Annotated[str, Query(min_length=1)],
    x_request_id: RequestIdHeader = None,
):
    """Compatibility endpoint; conflict_id remains explicit as a query key."""
    started = perf_counter()
    request_id = validate_request_id(x_request_id, body.request_id)
    data = await service.resolve_conflict(conflict_id, body)
    return success(request_id=request_id, data=data, started_at=started)


@router.post("/memory/search", response_model=SuccessResponse[SearchResponse])
async def search_memory(
    body: SearchRequest,
    service: Service,
    x_request_id: RequestIdHeader = None,
):
    started = perf_counter()
    request_id = validate_request_id(x_request_id, body.request_id)
    data = await service.search(body)
    return success(
        request_id=request_id,
        data=data,
        started_at=started,
        degraded=True,
        provider=Provider.DETERMINISTIC_TEST,
    )


@router.get(
    "/memory/transitions",
    response_model=SuccessResponse[list[dict]],
)
async def list_memory_transitions(
    query: Annotated[PreferenceHistoryQuery, Depends()],
    service: Service,
    x_request_id: RequestIdHeader = None,
):
    started = perf_counter()
    request_id = validate_request_id(x_request_id, query.request_id)
    data = await service.memory_transitions(query.user_id)
    return success(request_id=request_id, data=data, started_at=started)


@router.get(
    "/memory/{memory_id}",
    response_model=SuccessResponse[MemoryResponse],
)
async def get_memory(
    memory_id: str,
    query: Annotated[PreferenceHistoryQuery, Depends()],
    service: Service,
    x_request_id: RequestIdHeader = None,
):
    started = perf_counter()
    request_id = validate_request_id(x_request_id, query.request_id)
    data = await service.get_memory(query.user_id, memory_id)
    if data is None:
        raise HTTPException(status_code=404, detail="memory not found")
    return success(request_id=request_id, data=data, started_at=started)


@router.post(
    "/conflicts/{conflict_id}/resolve",
    response_model=SuccessResponse[ConflictResult],
)
async def resolve_conflict(
    conflict_id: str,
    body: ConflictResolveRequest,
    service: Service,
    x_request_id: RequestIdHeader = None,
):
    started = perf_counter()
    request_id = validate_request_id(x_request_id, body.request_id)
    data = await service.resolve_conflict(conflict_id, body)
    return success(request_id=request_id, data=data, started_at=started)


@router.post("/forget/preview", response_model=SuccessResponse[ForgetPlan])
async def preview_forget(
    body: ForgetPreviewRequest,
    service: Service,
    x_request_id: RequestIdHeader = None,
):
    started = perf_counter()
    request_id = validate_request_id(x_request_id, body.request_id)
    data = await service.preview_forget(body)
    return success(request_id=request_id, data=data, started_at=started)


@router.post("/forget/execute", response_model=SuccessResponse[ForgetResult])
async def execute_forget(
    body: ForgetExecuteRequest,
    service: Service,
    x_request_id: RequestIdHeader = None,
):
    started = perf_counter()
    request_id = validate_request_id(x_request_id, body.request_id)
    data = await service.execute_forget(body)
    return success(request_id=request_id, data=data, started_at=started)


@router.post(
    "/memory/promotions/run",
    response_model=SuccessResponse[PromotionResult],
)
async def run_promotions(
    body: PromotionRunRequest,
    service: Service,
    x_request_id: RequestIdHeader = None,
):
    started = perf_counter()
    request_id = validate_request_id(x_request_id, body.request_id)
    data = await service.run_promotions(body)
    return success(request_id=request_id, data=data, started_at=started)


@router.get("/health", response_model=SuccessResponse[HealthResponse])
async def health(
    service: Service,
    query: Annotated[HealthQuery, Depends()],
    x_request_id: RequestIdHeader = None,
):
    started = perf_counter()
    if query.request_id is not None:
        effective_request_id = validate_request_id(x_request_id, query.request_id)
    else:
        effective_request_id = x_request_id or f"req_{uuid4()}"
    data = await service.health()
    return success(
        request_id=effective_request_id,
        data=data,
        started_at=started,
        degraded=True,
        provider=Provider.DETERMINISTIC_TEST,
    )


@router.post(
    "/evaluations/run",
    response_model=SuccessResponse[EvaluationResult],
    status_code=202,
)
async def run_evaluation(
    body: EvaluationRunRequest,
    service: Service,
    x_request_id: RequestIdHeader = None,
):
    started = perf_counter()
    request_id = validate_request_id(x_request_id, body.request_id)
    data = await service.run_evaluation(body)
    return success(request_id=request_id, data=data, started_at=started)
