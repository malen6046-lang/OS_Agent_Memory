import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, select

from app.core.database import get_session, init_db
from app.dependencies.mock_services import (
    MockPreferenceService,
    MockRetriever,
    MockSafetyService,
    MockVectorStoreAdapter,
)
from app.models import AuditLogModel, MemoryRecordModel
from app.orchestrator import MemoryOrchestrator
from contracts.schemas.common import MemoryStatus
from contracts.schemas.forget import ForgetExecutionPlan
from contracts.schemas.knowledge import IngestResult
from contracts.schemas.memory import MemoryRecord
from repositories import (
    SQLiteAuditRepository,
    SQLiteIdempotencyRepository,
    SQLiteMemoryRepository,
)


def run(coroutine):
    return asyncio.run(coroutine)


class PersistingKnowledgeService:
    def ingest(self, events, preferences):
        event = events[0]
        return IngestResult(
            records=[
                MemoryRecord(
                    memory_id="mem_e2e_1",
                    user_id=event.user_id,
                    memory_kind="semantic",
                    subtype="fact",
                    content_text=str(event.payload["content"]),
                    content={"text": event.payload["content"]},
                    status="active",
                    confidence=0.9,
                    importance=0.8,
                    revision=1,
                    valid_from=event.occurred_at,
                    scene_tags=[event.scene],
                    source_refs=[event.source_event_id],
                    supersedes=[],
                    attributes={"embedding": [0.1, 0.2]},
                )
            ]
        )


class ForgetService:
    def execute(self, request):
        return ForgetExecutionPlan(
            request_id=request.request_id,
            user_id=request.user_id,
            plan_id=request.plan_id,
            memory_ids=request.selected_ids,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )


def orchestrator(vector_store):
    return MemoryOrchestrator(
        preference_service=MockPreferenceService(),
        knowledge_service=PersistingKnowledgeService(),
        retriever=MockRetriever(),
        forget_service=ForgetService(),
        safety_service=MockSafetyService(),
        idempotency_repository=SQLiteIdempotencyRepository(),
        repository=SQLiteMemoryRepository(),
        vector_store=vector_store,
        audit_repository=SQLiteAuditRepository(),
    )


def envelope():
    return {
        "contract_version": "1.0",
        "request_id": "req_e2e_ingest",
        "idempotency_key": "idem_e2e_ingest",
        "user_id": "usr_e2e",
        "session_id": None,
        "scene": "office",
        "source": "tool_result",
        "source_event_id": "event_e2e_1",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "payload": {"content": "Remember the release checklist."},
    }


def test_sqlite_ingest_replay_and_forget_survive_repository_restart(
    tmp_path: Path,
):
    database_path = tmp_path / "orchestration.db"
    init_db(database_path)
    vector_store = MockVectorStoreAdapter()
    first = orchestrator(vector_store)
    payload = envelope()

    ingested = run(first.ingest(payload))

    assert ingested["success"] is True
    assert ingested["data"]["vector_result"]["upserted"] == 1
    vector_pk = ingested["data"]["repository_result"]["vector_items"][0][
        "vector_pk"
    ]

    init_db(database_path)
    replayed = run(orchestrator(vector_store).ingest(payload))
    assert replayed["success"] is True
    assert replayed["meta"]["idempotent_replay"] is True

    forgotten = run(
        orchestrator(vector_store).execute_forget(
            {
                "request_id": "req_e2e_forget",
                "user_id": "usr_e2e",
                "plan_id": "plan_e2e_1",
                "confirmation_token": "confirm_e2e_1",
                "selected_ids": ["mem_e2e_1"],
            }
        )
    )

    assert forgotten["success"] is True
    assert forgotten["data"]["forget_result"]["vector_pks"] == [vector_pk]
    assert forgotten["data"]["vector_result"]["deleted"] == 1

    with get_session() as session:
        row = session.get(MemoryRecordModel, "mem_e2e_1")
        assert row.status == MemoryStatus.TOMBSTONED.value
        audit_count = session.scalar(select(func.count(AuditLogModel.audit_id)))
        assert audit_count == 2
