"""Knowledge ingestion and conflict contracts for V1.2.2."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from .common import MemorySubtype, NonEmptyString
from .memory import MemoryRecord


class KnowledgeDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: NonEmptyString
    source_event_id: NonEmptyString
    title: NonEmptyString
    knowledge_type: MemorySubtype
    body: NonEmptyString
    steps: list[NonEmptyString] = Field(default_factory=list)
    keywords: list[NonEmptyString] = Field(default_factory=list)
    source_uri: str | None = None
    source_reliability: float = Field(ge=0, le=1)
    effective_at: AwareDatetime


class ConflictDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relation: Literal[
        "duplicate",
        "support",
        "extend",
        "replace",
        "contradict",
        "unrelated",
    ]
    old_memory_id: NonEmptyString
    new_memory_id: NonEmptyString
    confidence: float = Field(ge=0, le=1)
    strategy: Literal["keep_old", "keep_new", "merge", "manual_review"]
    reason_codes: list[NonEmptyString] = Field(default_factory=list)


class IngestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: list[MemoryRecord] = Field(default_factory=list)
    conflicts: list[ConflictDecision] = Field(default_factory=list)
