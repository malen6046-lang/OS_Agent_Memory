"""Knowledge service Protocol frozen by CR-20260803-001."""

from typing import Protocol

from contracts.schemas.envelope import Envelope
from contracts.schemas.knowledge import ConflictDecision, IngestResult
from contracts.schemas.memory import MemoryRecord
from contracts.schemas.preference import PreferenceRecord


class KnowledgeService(Protocol):
    def ingest(
        self,
        events: list[Envelope],
        preferences: list[PreferenceRecord],
    ) -> IngestResult: ...

    def classify_conflict(
        self, old: MemoryRecord, new: MemoryRecord
    ) -> ConflictDecision: ...

    def apply_conflict(self, decision: ConflictDecision) -> MemoryRecord: ...
