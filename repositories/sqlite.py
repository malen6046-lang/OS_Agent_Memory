"""SQLAlchemy 2.0 SQLite implementations of persistence Protocols."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.models import AuditLogModel, IdempotencyRecordModel, MemoryRecordModel
from contracts.schemas.common import MemoryStatus
from contracts.schemas.forget import ForgetExecutionPlan
from contracts.schemas.memory import MemoryRecord
from contracts.schemas.persistence import (
    AuditEvent,
    AuditResult,
    IdempotencyEntry,
    IngestCommitResult,
    IngestServiceResult,
    LogicalDeleteResult,
)
from contracts.schemas.provider import VectorItem


SessionFactory = Callable[[], Session]
MAX_VECTOR_PK = 2**63 - 1


class RepositoryConflictError(RuntimeError):
    """A persisted identity conflicts with the requested operation."""


class RepositoryNotFoundError(RuntimeError):
    """A requested record does not exist in the user's scope."""


class SQLiteMemoryRepository:
    """Persist full memory contracts and stable vector-key mappings."""

    def __init__(self, session_factory: SessionFactory = get_session) -> None:
        self._session_factory = session_factory

    def commit_ingest(
        self,
        result: IngestServiceResult,
    ) -> IngestCommitResult:
        records = list(result.knowledge.records)
        vector_items: list[VectorItem] = []

        with self._session_factory() as session, session.begin():
            for record in records:
                row = session.get(MemoryRecordModel, record.memory_id)
                if row is None:
                    row = self._new_row(
                        record,
                        self._allocate_vector_pk(session, record.memory_id),
                    )
                    session.add(row)
                else:
                    self._update_row(row, record)

                vector = _embedding_from(record)
                if vector is not None:
                    vector_items.append(
                        VectorItem(
                            vector_pk=row.vector_pk,
                            memory_id=record.memory_id,
                            user_id=record.user_id,
                            status=record.status,
                            vector=vector,
                            metadata={
                                "memory_kind": record.memory_kind.value,
                                "subtype": record.subtype.value,
                                "revision": record.revision,
                            },
                        )
                    )

        return IngestCommitResult(
            records=records,
            vector_items=vector_items,
        )

    def get_by_ids(
        self,
        user_id: str,
        memory_ids: list[str],
        statuses: list[MemoryStatus] | None = None,
    ) -> list[MemoryRecord]:
        if not memory_ids or statuses == []:
            return []

        unique_ids = list(dict.fromkeys(memory_ids))
        conditions = [
            MemoryRecordModel.user_id == user_id,
            MemoryRecordModel.memory_id.in_(unique_ids),
        ]
        if statuses is not None:
            conditions.append(
                MemoryRecordModel.status.in_(
                    [status.value for status in statuses]
                )
            )

        with self._session_factory() as session:
            rows = list(
                session.scalars(
                    select(MemoryRecordModel).where(*conditions)
                )
            )
            records_by_id = {
                row.memory_id: _record_from_row(row)
                for row in rows
                if row.record_json
            }
            return [
                records_by_id[memory_id]
                for memory_id in memory_ids
                if memory_id in records_by_id
            ]

    def logical_delete(
        self,
        plan: ForgetExecutionPlan,
    ) -> LogicalDeleteResult:
        memory_ids = list(dict.fromkeys(plan.memory_ids))

        with self._session_factory() as session, session.begin():
            rows = list(
                session.scalars(
                    select(MemoryRecordModel).where(
                        MemoryRecordModel.user_id == plan.user_id,
                        MemoryRecordModel.memory_id.in_(memory_ids),
                    )
                )
            )
            rows_by_id = {row.memory_id: row for row in rows}
            missing = [item for item in memory_ids if item not in rows_by_id]
            if missing:
                raise RepositoryNotFoundError(
                    "memory records not found in user scope: "
                    + ", ".join(missing)
                )

            vector_pks: list[int] = []
            for memory_id in memory_ids:
                row = rows_by_id[memory_id]
                if row.vector_pk is None:
                    row.vector_pk = self._allocate_vector_pk(session, memory_id)
                vector_pks.append(row.vector_pk)

                if row.status == MemoryStatus.TOMBSTONED.value:
                    continue
                record = _record_from_row(row)
                tombstoned = record.model_copy(
                    update={
                        "status": MemoryStatus.TOMBSTONED,
                        "revision": record.revision + 1,
                        "valid_to": datetime.now(timezone.utc),
                    }
                )
                self._update_row(row, tombstoned)

        return LogicalDeleteResult(
            plan_id=plan.plan_id,
            user_id=plan.user_id,
            memory_ids=memory_ids,
            vector_pks=vector_pks,
        )

    @staticmethod
    def _new_row(record: MemoryRecord, vector_pk: int) -> MemoryRecordModel:
        return MemoryRecordModel(
            memory_id=record.memory_id,
            user_id=record.user_id,
            memory_kind=record.memory_kind.value,
            content_text=record.content_text,
            status=record.status.value,
            confidence=record.confidence,
            revision=record.revision,
            vector_pk=vector_pk,
            record_json=record.model_dump(mode="json"),
            created_at=record.valid_from,
            updated_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _update_row(row: MemoryRecordModel, record: MemoryRecord) -> None:
        if row.user_id != record.user_id:
            raise RepositoryConflictError(
                "memory_id already belongs to another user"
            )
        if record.revision < row.revision:
            raise RepositoryConflictError(
                "memory revision cannot move backwards"
            )

        row.memory_kind = record.memory_kind.value
        row.content_text = record.content_text
        row.status = record.status.value
        row.confidence = record.confidence
        row.revision = record.revision
        row.record_json = record.model_dump(mode="json")
        row.updated_at = datetime.now(timezone.utc)

    @staticmethod
    def _allocate_vector_pk(session: Session, memory_id: str) -> int:
        candidate = _stable_vector_pk(memory_id)
        while True:
            owner = session.scalar(
                select(MemoryRecordModel.memory_id).where(
                    MemoryRecordModel.vector_pk == candidate
                )
            )
            if owner is None or owner == memory_id:
                return candidate
            candidate = (candidate + 1) & MAX_VECTOR_PK


class SQLiteIdempotencyRepository:
    """Persist replay responses without storing request bodies."""

    def __init__(self, session_factory: SessionFactory = get_session) -> None:
        self._session_factory = session_factory

    def get(
        self,
        user_id: str,
        operation: str,
        idempotency_key: str,
    ) -> IdempotencyEntry | None:
        with self._session_factory() as session:
            row = session.get(IdempotencyRecordModel, idempotency_key)
            if row is None:
                return None
            if row.user_id != user_id or row.operation != operation:
                return None
            return IdempotencyEntry(
                user_id=row.user_id,
                operation=row.operation,
                idempotency_key=row.idempotency_key,
                fingerprint=row.fingerprint,
                response=row.response_json,
            )

    def save(self, entry: IdempotencyEntry) -> None:
        with self._session_factory() as session, session.begin():
            row = session.get(
                IdempotencyRecordModel,
                entry.idempotency_key,
            )
            if row is not None:
                if (
                    row.user_id == entry.user_id
                    and row.operation == entry.operation
                    and row.fingerprint == entry.fingerprint
                ):
                    return
                raise RepositoryConflictError(
                    "idempotency key already belongs to another request"
                )

            session.add(
                IdempotencyRecordModel(
                    idempotency_key=entry.idempotency_key,
                    user_id=entry.user_id,
                    operation=entry.operation,
                    request_id=_response_request_id(entry),
                    fingerprint=entry.fingerprint,
                    response_json=entry.response,
                )
            )


class SQLiteAuditRepository:
    """Append structured audit metadata without persisting request content."""

    def __init__(self, session_factory: SessionFactory = get_session) -> None:
        self._session_factory = session_factory

    def record(self, event: AuditEvent) -> AuditResult:
        audit_id = f"audit_{uuid4().hex}"
        with self._session_factory() as session, session.begin():
            session.add(
                AuditLogModel(
                    audit_id=audit_id,
                    operation=event.operation,
                    operator=event.user_id,
                    user_id=event.user_id,
                    request_id=event.request_id,
                    metadata_json=event.metadata,
                )
            )
        return AuditResult(audit_id=audit_id)


def _stable_vector_pk(memory_id: str) -> int:
    digest = hashlib.blake2b(
        memory_id.encode("utf-8"),
        digest_size=8,
        person=b"os-memory",
    ).digest()
    return int.from_bytes(digest, "big") & MAX_VECTOR_PK


def _embedding_from(record: MemoryRecord) -> list[float] | None:
    value: Any = record.attributes.get("embedding")
    if value is None:
        return None
    if not isinstance(value, list) or not value:
        raise ValueError("attributes.embedding must be a non-empty list")

    vector: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError("attributes.embedding must contain numbers")
        number = float(item)
        if not math.isfinite(number):
            raise ValueError("attributes.embedding must contain finite numbers")
        vector.append(number)
    return vector


def _record_from_row(row: MemoryRecordModel) -> MemoryRecord:
    if not row.record_json:
        raise RepositoryConflictError(
            f"memory record {row.memory_id!r} has no contract payload"
        )
    return MemoryRecord.model_validate(row.record_json)


def _response_request_id(entry: IdempotencyEntry) -> str:
    request_id = entry.response.get("request_id")
    if isinstance(request_id, str) and request_id.strip():
        return request_id
    return entry.idempotency_key
