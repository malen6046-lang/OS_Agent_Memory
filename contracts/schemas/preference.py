"""PreferenceRecord from Module Interface Plan V1.2."""

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from .common import (
    MemoryStatus,
    NonEmptyString,
    PreferencePolarity,
    PreferenceScope,
)


class PreferenceCandidate(BaseModel):
    """A not-yet-persisted preference extracted from source evidence."""

    model_config = ConfigDict(extra="forbid")

    user_id: NonEmptyString
    preference_key: NonEmptyString
    value: JsonValue
    category: NonEmptyString
    scope: PreferenceScope
    scope_value: NonEmptyString
    polarity: PreferencePolarity
    confidence: float = Field(ge=0, le=1)
    evidence: list[dict[str, JsonValue]] = Field(default_factory=list)


class PreferenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preference_key: NonEmptyString
    value: JsonValue
    category: NonEmptyString
    scope: PreferenceScope
    scope_value: NonEmptyString
    polarity: PreferencePolarity
    confidence: float = Field(ge=0, le=1)
    evidence_count: int = Field(ge=0)
    evidence: list[dict[str, JsonValue]]
    revision: int = Field(ge=1)
    status: MemoryStatus

    @field_validator("evidence")
    @classmethod
    def evidence_ids_must_be_non_empty(
        cls, evidence: list[dict[str, JsonValue]]
    ) -> list[dict[str, JsonValue]]:
        for item in evidence:
            for key, value in item.items():
                if key.endswith("_id") and (
                    not isinstance(value, str) or not value.strip()
                ):
                    raise ValueError(f"{key} must be a non-empty string")
        return evidence
