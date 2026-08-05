from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select

from app.core.database import (
    SqlAlchemyUnitOfWork,
    create_session_factory,
    create_sqlite_engine,
)
from app.core.dependencies import get_api_service
from app.core.errors import AppError
from app.main import app
from app.models import AuditLogModel, Base, IdempotencyRecordModel
from app.repositories.in_memory import InMemoryRepository
from app.services.platform import MemoryApiService
from contracts.schemas import (
    ErrorCode,
    ErrorResponse,
    EvaluationResult,
    EventIngestItem,
    EventIngestResult,
    ForgetPlan,
    ForgetResult,
    HealthResponse,
    ItemOutcome,
    KnowledgeIngestResult,
    OperationStatus,
    PreferenceExtractResult,
    PreferenceListResult,
    PromotionResult,
    ConflictResult,
    SearchRequest,
    SearchResponse,
    SuccessResponse,
)


def event_payload(
    *,
    request_id: str = "req_httpx",
    idempotency_key: str = "idem_httpx",
    source_event_id: str = "evt_httpx",
) -> dict:
    return {
        "contract_version": "1.0",
        "request_id": request_id,
        "idempotency_key": idempotency_key,
        "user_id": "usr_httpx",
        "session_id": "ses_httpx",
        "scene": "office_automation",
        "source": "manual_config",
        "source_event_id": source_event_id,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "payload": {"content": "使用表格输出"},
    }


def search_payload() -> dict:
    return {
        "request_id": "req_search",
        "user_id": "usr_httpx",
        "query": "如何生成表格？",
        "filters": {
            "scene": "office_automation",
            "memory_kinds": ["semantic"],
            "attributes": {},
        },
        "top_k": 5,
    }


def forget_preview_payload() -> dict:
    return {
        "request_id": "req_forget_preview",
        "user_id": "usr_httpx",
        "instruction": "忘记表格输出偏好",
        "scene": "office_automation",
    }


def forget_execute_payload(memory_id: str = "mem_missing") -> dict:
    return {
        "request_id": "req_forget_execute",
        "idempotency_key": "idem_forget_execute",
        "user_id": "usr_httpx",
        "source_event_id": "evt_forget_execute",
        "confirmation_token": "confirm_httpx",
        "selected_ids": [memory_id],
    }


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def test_database(tmp_path):
    database_path = tmp_path / "api-integration.sqlite3"
    engine = create_sqlite_engine(f"sqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    try:
        yield engine, session_factory, database_path
    finally:
        engine.dispose()


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as http_client:
        yield http_client
    app.dependency_overrides.clear()


def assert_error_schema(response: httpx.Response, status_code: int) -> ErrorResponse:
    assert response.status_code == status_code, response.text
    return ErrorResponse.model_validate(response.json())


class SqliteIdempotencyRepository:
    """测试专用：只在 pytest 临时 SQLite 中记录事件幂等键。"""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    async def save_events(self, events) -> list[bool]:
        created: list[bool] = []
        for event in events:
            with SqlAlchemyUnitOfWork(self._session_factory) as uow:
                existing = uow.session.scalar(
                    select(IdempotencyRecordModel).where(
                        IdempotencyRecordModel.user_id == event.user_id,
                        IdempotencyRecordModel.operation == "events.ingest",
                        IdempotencyRecordModel.idempotency_key
                        == event.idempotency_key,
                    )
                )
                if existing is not None:
                    created.append(False)
                    continue
                now = datetime.now(timezone.utc)
                uow.session.add(
                    IdempotencyRecordModel(
                        record_id=f"idem_{uuid4()}",
                        user_id=event.user_id,
                        operation="events.ingest",
                        idempotency_key=event.idempotency_key,
                        request_hash=sha256(
                            event.model_dump_json().encode("utf-8")
                        ).hexdigest(),
                        response=None,
                        created_at=now,
                        expires_at=now + timedelta(hours=24),
                    )
                )
                created.append(True)
        return created


class PersistentTestService(MemoryApiService):
    async def ingest_events(self, events) -> EventIngestResult:
        created = await self._repository.save_events(events)
        return EventIngestResult(
            status=OperationStatus.ACCEPTED,
            items=[
                EventIngestItem(
                    source_event_id=event.source_event_id,
                    outcome=(
                        ItemOutcome.CREATED
                        if was_created
                        else ItemOutcome.DUPLICATE
                    ),
                    memory_ids=(
                        [f"mem_{event.source_event_id}"] if was_created else []
                    ),
                )
                for event, was_created in zip(events, created, strict=True)
            ],
        )


class AlgorithmFailureService(MemoryApiService):
    async def search(self, request: SearchRequest):
        raise AppError(
            ErrorCode.EMBEDDING_RUNTIME_FAILED,
            "Embedding 算法服务执行失败",
            status_code=503,
            retryable=True,
            request_id=request.request_id,
        )


class TransactionFailureService(MemoryApiService):
    def __init__(self, repository, session_factory) -> None:
        super().__init__(repository)
        self._session_factory = session_factory

    async def ingest_events(self, events):
        event = events[0]
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            uow.session.add(
                AuditLogModel(
                    audit_id=f"audit_{uuid4()}",
                    request_id=event.request_id,
                    user_id=event.user_id,
                    operation="events.ingest",
                    target_ids=[event.source_event_id],
                    details={"phase": "before_forced_failure"},
                    created_at=datetime.now(timezone.utc),
                )
            )
            uow.session.flush()
            raise AppError(
                ErrorCode.STORAGE_WRITE_FAILED,
                "模拟数据库事务失败",
                status_code=503,
                retryable=True,
                request_id=event.request_id,
            )


@pytest.mark.anyio
async def test_normal_request_and_response_matches_schema(client):
    response = await client.post(
        "/api/v1/events/ingest", json={"events": [event_payload()]}
    )
    assert response.status_code == 200
    parsed = SuccessResponse[EventIngestResult].model_validate(response.json())
    assert parsed.success is True
    assert parsed.data.items[0].outcome is ItemOutcome.CREATED


@pytest.mark.anyio
async def test_missing_required_field_returns_schema_error(client):
    payload = search_payload()
    payload.pop("query")
    response = await client.post("/api/v1/memory/search", json=payload)
    error = assert_error_schema(response, 422)
    assert error.error.code is ErrorCode.VALIDATION_ERROR
    assert any(item["loc"][-1] == "query" for item in error.error.details["errors"])


@pytest.mark.anyio
async def test_illegal_enum_returns_schema_error(client):
    payload = search_payload()
    payload["filters"]["memory_kinds"] = ["not_a_memory_kind"]
    response = await client.post("/api/v1/memory/search", json=payload)
    error = assert_error_schema(response, 422)
    assert error.error.code is ErrorCode.VALIDATION_ERROR


@pytest.mark.anyio
async def test_nonexistent_memory_id_is_reported_without_false_deletion(client):
    response = await client.post(
        "/api/v1/forget/execute",
        json=forget_execute_payload("mem_does_not_exist"),
    )
    assert response.status_code == 200
    parsed = SuccessResponse[ForgetResult].model_validate(response.json())
    assert parsed.data.tombstoned_ids == []
    assert parsed.data.failed_items[0].memory_id == "mem_does_not_exist"
    assert parsed.data.failed_items[0].code is ErrorCode.STORAGE_WRITE_FAILED


@pytest.mark.anyio
async def test_duplicate_write_uses_temporary_sqlite(
    client, test_database
):
    _, session_factory, database_path = test_database
    service = PersistentTestService(SqliteIdempotencyRepository(session_factory))
    app.dependency_overrides[get_api_service] = lambda: service
    payload = {"events": [event_payload()]}

    first = await client.post("/api/v1/events/ingest", json=payload)
    second = await client.post("/api/v1/events/ingest", json=payload)

    first_body = SuccessResponse[EventIngestResult].model_validate(first.json())
    second_body = SuccessResponse[EventIngestResult].model_validate(second.json())
    assert first_body.data.items[0].outcome is ItemOutcome.CREATED
    assert second_body.data.items[0].outcome is ItemOutcome.DUPLICATE
    assert database_path.exists()
    with session_factory() as session:
        count = session.scalar(select(func.count(IdempotencyRecordModel.record_id)))
    assert count == 1


@pytest.mark.anyio
async def test_algorithm_service_exception_uses_unified_error_schema(client):
    service = AlgorithmFailureService(InMemoryRepository())
    app.dependency_overrides[get_api_service] = lambda: service

    response = await client.post("/api/v1/memory/search", json=search_payload())

    error = assert_error_schema(response, 503)
    assert error.error.code is ErrorCode.EMBEDDING_RUNTIME_FAILED
    assert error.error.retryable is True


@pytest.mark.anyio
async def test_database_transaction_failure_rolls_back(
    client, test_database
):
    _, session_factory, _ = test_database
    service = TransactionFailureService(InMemoryRepository(), session_factory)
    app.dependency_overrides[get_api_service] = lambda: service

    response = await client.post(
        "/api/v1/events/ingest",
        json={"events": [event_payload(request_id="req_rollback")]},
    )

    error = assert_error_schema(response, 503)
    assert error.error.code is ErrorCode.STORAGE_WRITE_FAILED
    with session_factory() as session:
        count = session.scalar(select(func.count(AuditLogModel.audit_id)))
    assert count == 0


@pytest.mark.anyio
async def test_forget_preview_and_execute_match_schemas(client):
    preview_response = await client.post(
        "/api/v1/forget/preview", json=forget_preview_payload()
    )
    execute_response = await client.post(
        "/api/v1/forget/execute", json=forget_execute_payload()
    )

    assert preview_response.status_code == 200
    assert execute_response.status_code == 200
    preview = SuccessResponse[ForgetPlan].model_validate(preview_response.json())
    execute = SuccessResponse[ForgetResult].model_validate(execute_response.json())
    assert preview.data.confirmation_token
    assert execute.data.audit_id


@pytest.mark.anyio
async def test_health_check_matches_schema(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    parsed = SuccessResponse[HealthResponse].model_validate(response.json())
    assert parsed.data.contract_version == "1.0"
    assert "api" in parsed.data.components


@pytest.mark.anyio
async def test_remaining_v11_endpoints_use_httpx_and_match_schemas(client):
    now = datetime.now(timezone.utc).isoformat()
    cases = [
        (
            "POST",
            "/api/v1/preferences/extract",
            {"json": {"events": [event_payload(request_id="req_pref_extract")]}},
            200,
            SuccessResponse[PreferenceExtractResult],
        ),
        (
            "GET",
            "/api/v1/preferences",
            {
                "params": {
                    "request_id": "req_pref_list",
                    "user_id": "usr_httpx",
                    "scene": "office_automation",
                }
            },
            200,
            SuccessResponse[PreferenceListResult],
        ),
        (
            "GET",
            "/api/v1/preferences/output.format/history",
            {
                "params": {
                    "request_id": "req_pref_history",
                    "user_id": "usr_httpx",
                }
            },
            200,
            SuccessResponse[PreferenceListResult],
        ),
        (
            "POST",
            "/api/v1/knowledge/ingest",
            {
                "json": {
                    "request_id": "req_knowledge",
                    "idempotency_key": "idem_knowledge",
                    "user_id": "usr_httpx",
                    "source_event_id": "evt_knowledge",
                    "records": [
                        {
                            "title": "表格输出流程",
                            "knowledge_type": "workflow",
                            "body": "生成并检查表格",
                            "steps": ["生成表格", "检查格式"],
                            "keywords": ["表格"],
                            "source_uri": None,
                            "source_reliability": 0.8,
                            "effective_at": now,
                        }
                    ],
                }
            },
            200,
            SuccessResponse[KnowledgeIngestResult],
        ),
        (
            "POST",
            "/api/v1/conflicts/cfl_httpx/resolve",
            {
                "json": {
                    "request_id": "req_conflict",
                    "idempotency_key": "idem_conflict",
                    "user_id": "usr_httpx",
                    "source_event_id": "evt_conflict",
                    "decision": {
                        "relation": "replace",
                        "old_memory_id": "mem_old",
                        "new_memory_id": "mem_new",
                        "confidence": 0.9,
                        "strategy": "keep_new",
                        "reason_codes": ["newer_effective_at"],
                    },
                }
            },
            200,
            SuccessResponse[ConflictResult],
        ),
        (
            "POST",
            "/api/v1/memory/promotions/run",
            {
                "json": {
                    "request_id": "req_promotion",
                    "idempotency_key": "idem_promotion",
                    "user_id": "usr_httpx",
                    "source_event_id": "evt_promotion",
                    "scene": "office_automation",
                }
            },
            200,
            SuccessResponse[PromotionResult],
        ),
        (
            "POST",
            "/api/v1/evaluations/run",
            {
                "json": {
                    "request_id": "req_evaluation",
                    "user_id": "usr_httpx",
                    "evaluation_types": ["retrieval", "performance"],
                    "attributes": {},
                }
            },
            202,
            SuccessResponse[EvaluationResult],
        ),
    ]

    for method, path, kwargs, expected_status, response_schema in cases:
        response = await client.request(method, path, **kwargs)
        assert response.status_code == expected_status, (
            f"{method} {path}: {response.text}"
        )
        response_schema.model_validate(response.json())

    search_response = await client.post(
        "/api/v1/memory/search", json=search_payload()
    )
    SuccessResponse[SearchResponse].model_validate(search_response.json())
