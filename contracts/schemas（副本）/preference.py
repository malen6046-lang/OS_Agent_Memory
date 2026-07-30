from pydantic import Field, model_validator

from contracts.schemas.base import ContractModel, JsonValue, NonBlankStr, UnitInterval
from contracts.schemas.common import Envelope
from contracts.schemas.enums import (
    MemoryStatus,
    PreferenceCategory,
    PreferencePolarity,
    PreferenceScope,
)


class Evidence(ContractModel):
    source_event_id: NonBlankStr
    weight: UnitInterval


class PreferenceCreate(ContractModel):
    user_id: NonBlankStr
    preference_key: NonBlankStr
    value: JsonValue
    category: PreferenceCategory
    scope: PreferenceScope
    scope_value: NonBlankStr | None = None
    polarity: PreferencePolarity
    confidence: UnitInterval
    evidence: list[Evidence] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_scope_value(self) -> "PreferenceCreate":
        if self.scope is PreferenceScope.GLOBAL and self.scope_value is not None:
            raise ValueError("scope_value must be null when scope is global")
        if self.scope in {PreferenceScope.SCENE, PreferenceScope.TOOL} and self.scope_value is None:
            raise ValueError("scope_value is required when scope is scene or tool")
        return self


class PreferenceUpdate(ContractModel):
    value: JsonValue | None = None
    polarity: PreferencePolarity | None = None
    confidence: UnitInterval | None = None
    evidence: list[Evidence] | None = None
    expected_revision: int = Field(strict=True, ge=1)

    @model_validator(mode="after")
    def at_least_one_change(self) -> "PreferenceUpdate":
        if not (self.model_fields_set - {"expected_revision"}):
            raise ValueError("at least one updatable field is required")
        return self


class PreferenceResponse(PreferenceCreate):
    evidence_count: int = Field(strict=True, ge=0)
    revision: int = Field(strict=True, ge=1)
    status: MemoryStatus

    @model_validator(mode="after")
    def evidence_count_matches(self) -> "PreferenceResponse":
        if self.evidence_count != len(self.evidence):
            raise ValueError("evidence_count must equal evidence length")
        return self


PreferenceRecord = PreferenceResponse


class PreferenceCandidate(PreferenceCreate):
    pass


class PreferenceExtractRequest(ContractModel):
    events: list[Envelope] = Field(min_length=1)


class PreferenceExtractResult(ContractModel):
    candidates: list[PreferenceCandidate] = Field(default_factory=list)


class PreferenceQuery(ContractModel):
    request_id: NonBlankStr
    user_id: NonBlankStr
    scene: NonBlankStr
    keys: list[NonBlankStr] | None = None


class PreferenceHistoryQuery(ContractModel):
    request_id: NonBlankStr
    user_id: NonBlankStr


class PreferenceListResult(ContractModel):
    items: list[PreferenceResponse] = Field(default_factory=list)
