from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.database import get_session, init_db
from app.models import AuditLogModel, MemoryRecordModel
from contracts.schemas.common import MemoryKind, MemoryStatus, MemorySubtype
from contracts.schemas.forget import ForgetExecutionPlan
from contracts.schemas.knowledge import IngestResult
from contracts.schemas.memory import MemoryRecord
from contracts.schemas.persistence import (
    AuditEvent,
    IdempotencyEntry,
    IngestServiceResult,
)
from repositories.sqlite import (
    RepositoryConflictError,
    RepositoryNotFoundError,
    SQLiteAuditRepository,
    SQLiteIdempotencyRepository,
    SQLiteMemoryRepository,
)


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    path = tmp_path / "repository.db"
    init_db(path)
    return path


def memory_record(
    *,
    memory_id: str = "mem_1",
    user_id: str = "usr_1",
    revision: int = 1,
    embedding: list[float] | None = None,
) -> MemoryRecord:
    attributes = {}
    if embedding is not None:
        attributes["embedding"] = embedding
    return MemoryRecord(
        memory_id=memory_id,
        user_id=user_id,
        memory_kind=MemoryKind.SEMANTIC,
        subtype=MemorySubtype.FACT,
        content_text="The user prefers concise status updates.",
        content={"subject": "status updates"},
        status=MemoryStatus.ACTIVE,
        confidence=0.9,
        importance=0.8,
        revision=revision,
        valid_from=datetime.now(timezone.utc),
        scene_tags=["work"],
        source_refs=["event_1"],
        supersedes=[],
        attributes=attributes,
    )


def ingest_result(record: MemoryRecord) -> IngestServiceResult:
    return IngestServiceResult(
        knowledge=IngestResult(records=[record]),
    )


def test_commit_ingest_persists_full_contract_and_vector_mapping(database_path):
    repository = SQLiteMemoryRepository()
    record = memory_record(embedding=[0.1, 0.2, 0.3])

    result = repository.commit_ingest(ingest_result(record))

    assert result.records == [record]
    assert len(result.vector_items) == 1
    item = result.vector_items[0]
    assert 0 <= item.vector_pk <= 2**63 - 1
    assert item.memory_id == record.memory_id
    assert item.vector == [0.1, 0.2, 0.3]

    with get_session() as session:
        row = session.get(MemoryRecordModel, record.memory_id)
        assert row is not None
        assert row.vector_pk == item.vector_pk
        assert MemoryRecord.model_validate(row.record_json) == record

    init_db(database_path)
    repeated = SQLiteMemoryRepository().commit_ingest(ingest_result(record))
    assert repeated.vector_items[0].vector_pk == item.vector_pk


def test_commit_without_embedding_persists_but_does_not_forge_vector(
    database_path,
):
    result = SQLiteMemoryRepository().commit_ingest(
        ingest_result(memory_record())
    )

    assert len(result.records) == 1
    assert result.vector_items == []


def test_get_by_ids_preserves_order_and_enforces_user_and_status(database_path):
    repository = SQLiteMemoryRepository()
    repository.commit_ingest(ingest_result(memory_record(memory_id="mem_1")))
    repository.commit_ingest(ingest_result(memory_record(memory_id="mem_2")))
    repository.commit_ingest(
        ingest_result(memory_record(memory_id="mem_other", user_id="usr_2"))
    )

    records = repository.get_by_ids(
        "usr_1",
        ["mem_2", "mem_other", "mem_1"],
        [MemoryStatus.ACTIVE],
    )

    assert [record.memory_id for record in records] == ["mem_2", "mem_1"]
    assert repository.get_by_ids(
        "usr_2", ["mem_1"], [MemoryStatus.ACTIVE]
    ) == []

    plan = ForgetExecutionPlan(
        request_id="req_forget",
        user_id="usr_1",
        plan_id="plan_read_filter",
        memory_ids=["mem_1"],
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    repository.logical_delete(plan)

    assert repository.get_by_ids(
        "usr_1", ["mem_1"], [MemoryStatus.ACTIVE]
    ) == []
    assert repository.get_by_ids(
        "usr_1", ["mem_1"], [MemoryStatus.TOMBSTONED]
    )[0].status == MemoryStatus.TOMBSTONED


def test_commit_rejects_cross_user_identity_and_revision_rollback(database_path):
    repository = SQLiteMemoryRepository()
    repository.commit_ingest(ingest_result(memory_record()))

    with pytest.raises(RepositoryConflictError, match="another user"):
        repository.commit_ingest(
            ingest_result(memory_record(user_id="usr_2", revision=2))
        )

    repository.commit_ingest(ingest_result(memory_record(revision=2)))
    with pytest.raises(RepositoryConflictError, match="move backwards"):
        repository.commit_ingest(ingest_result(memory_record(revision=1)))


def test_logical_delete_tombstones_and_returns_precise_stable_pk(database_path):
    repository = SQLiteMemoryRepository()
    committed = repository.commit_ingest(
        ingest_result(memory_record(embedding=[0.25]))
    )
    vector_pk = committed.vector_items[0].vector_pk
    plan = ForgetExecutionPlan(
        request_id="req_forget",
        user_id="usr_1",
        plan_id="plan_1",
        memory_ids=["mem_1"],
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )

    deleted = repository.logical_delete(plan)

    assert deleted.memory_ids == ["mem_1"]
    assert deleted.vector_pks == [vector_pk]
    with get_session() as session:
        row = session.get(MemoryRecordModel, "mem_1")
        persisted = MemoryRecord.model_validate(row.record_json)
        assert row.status == MemoryStatus.TOMBSTONED.value
        assert persisted.status == MemoryStatus.TOMBSTONED
        assert persisted.revision == 2
        assert persisted.valid_to is not None

    repeated = repository.logical_delete(plan)
    assert repeated.vector_pks == [vector_pk]


def test_logical_delete_enforces_user_scope_and_is_atomic(database_path):
    repository = SQLiteMemoryRepository()
    repository.commit_ingest(ingest_result(memory_record()))
    plan = ForgetExecutionPlan(
        request_id="req_forget",
        user_id="usr_other",
        plan_id="plan_1",
        memory_ids=["mem_1"],
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )

    with pytest.raises(RepositoryNotFoundError, match="not found"):
        repository.logical_delete(plan)

    with get_session() as session:
        row = session.get(MemoryRecordModel, "mem_1")
        assert row.status == MemoryStatus.ACTIVE.value


def test_idempotency_response_survives_repository_restart(database_path):
    entry = IdempotencyEntry(
        user_id="usr_1",
        operation="ingest",
        idempotency_key="idem_1",
        fingerprint="fingerprint_1",
        response={
            "success": True,
            "request_id": "req_1",
            "data": {"stored": 1},
        },
    )
    SQLiteIdempotencyRepository().save(entry)

    init_db(database_path)
    loaded = SQLiteIdempotencyRepository().get(
        "usr_1",
        "ingest",
        "idem_1",
    )

    assert loaded == entry
    assert SQLiteIdempotencyRepository().get(
        "usr_other", "ingest", "idem_1"
    ) is None


def test_idempotency_key_conflict_is_rejected(database_path):
    repository = SQLiteIdempotencyRepository()
    first = IdempotencyEntry(
        user_id="usr_1",
        operation="ingest",
        idempotency_key="idem_1",
        fingerprint="fingerprint_1",
        response={"request_id": "req_1"},
    )
    repository.save(first)
    repository.save(first)

    with pytest.raises(RepositoryConflictError, match="another request"):
        repository.save(
            first.model_copy(update={"fingerprint": "fingerprint_2"})
        )


def test_audit_repository_persists_structured_metadata(database_path):
    event = AuditEvent(
        operation="memory.forget",
        request_id="req_1",
        user_id="usr_1",
        metadata={"memory_ids": ["mem_1"], "deleted_count": 1},
    )

    result = SQLiteAuditRepository().record(event)

    assert result.audit_id.startswith("audit_")
    with get_session() as session:
        row = session.scalar(
            select(AuditLogModel).where(
                AuditLogModel.audit_id == result.audit_id
            )
        )
        assert row is not None
        assert row.user_id == "usr_1"
        assert row.metadata_json == event.metadata
