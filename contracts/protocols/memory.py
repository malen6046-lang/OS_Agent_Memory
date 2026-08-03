"""Persistence Protocols frozen by CR-20260803-001."""

from typing import Protocol

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


class MemoryRepository(Protocol):
    def commit_ingest(
        self, result: IngestServiceResult
    ) -> IngestCommitResult: ...

    def get_by_ids(
        self,
        user_id: str,
        memory_ids: list[str],
        statuses: list[MemoryStatus] | None = None,
    ) -> list[MemoryRecord]: ...

    def logical_delete(
        self, plan: ForgetExecutionPlan
    ) -> LogicalDeleteResult: ...


class IdempotencyRepository(Protocol):
    def get(
        self,
        user_id: str,
        operation: str,
        idempotency_key: str,
    ) -> IdempotencyEntry | None: ...

    def save(self, entry: IdempotencyEntry) -> None: ...


class AuditRepository(Protocol):
    def record(self, event: AuditEvent) -> AuditResult: ...
