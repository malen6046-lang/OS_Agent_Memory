"""MemoryRecord from Module Interface Plan V1.2."""

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue

from .common import (
    MemoryKind,
    MemoryStatus,
    MemorySubtype,
    NonEmptyString,
)


class MemoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: NonEmptyString
    user_id: NonEmptyString
    memory_kind: MemoryKind
    subtype: MemorySubtype
    content_text: NonEmptyString
    content: dict[str, JsonValue]
    status: MemoryStatus
    confidence: float = Field(ge=0, le=1)
    importance: float = Field(ge=0, le=1)
    revision: int = Field(ge=1)
    valid_from: AwareDatetime
    valid_to: AwareDatetime | None = None
    expires_at: AwareDatetime | None = None
    scene_tags: list[str]
    source_refs: list[NonEmptyString]
    supersedes: list[NonEmptyString]
    attributes: dict[str, JsonValue]
