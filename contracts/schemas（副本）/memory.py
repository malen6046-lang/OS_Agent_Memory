from pydantic import AwareDatetime, Field, model_validator

from contracts.schemas.base import ContractModel, JsonObject, NonBlankStr, UnitInterval
from contracts.schemas.enums import MemoryKind, MemoryStatus, MemorySubtype


class MemoryCreate(ContractModel):
    user_id: NonBlankStr
    memory_kind: MemoryKind
    subtype: MemorySubtype
    content_text: NonBlankStr
    content: JsonObject
    confidence: UnitInterval
    importance: UnitInterval
    valid_from: AwareDatetime
    valid_to: AwareDatetime | None = None
    expires_at: AwareDatetime | None = None
    scene_tags: list[NonBlankStr] = Field(default_factory=list)
    source_refs: list[NonBlankStr] = Field(min_length=1)
    supersedes: list[NonBlankStr] = Field(default_factory=list)
    attributes: JsonObject = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_time_order(self) -> "MemoryCreate":
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("valid_to must not be earlier than valid_from")
        if self.expires_at is not None and self.expires_at < self.valid_from:
            raise ValueError("expires_at must not be earlier than valid_from")
        return self


class MemoryUpdate(ContractModel):
    content_text: NonBlankStr | None = None
    content: JsonObject | None = None
    confidence: UnitInterval | None = None
    importance: UnitInterval | None = None
    valid_from: AwareDatetime | None = None
    valid_to: AwareDatetime | None = None
    expires_at: AwareDatetime | None = None
    scene_tags: list[NonBlankStr] | None = None
    source_refs: list[NonBlankStr] | None = None
    supersedes: list[NonBlankStr] | None = None
    attributes: JsonObject | None = None
    expected_revision: int = Field(strict=True, ge=1)

    @model_validator(mode="after")
    def validate_update(self) -> "MemoryUpdate":
        if not (self.model_fields_set - {"expected_revision"}):
            raise ValueError("at least one updatable field is required")
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to must not be earlier than valid_from")
        if self.valid_from and self.expires_at and self.expires_at < self.valid_from:
            raise ValueError("expires_at must not be earlier than valid_from")
        return self


class MemoryResponse(MemoryCreate):
    memory_id: NonBlankStr
    status: MemoryStatus
    revision: int = Field(strict=True, ge=1)


MemoryRecord = MemoryResponse
