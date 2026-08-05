from pydantic import AwareDatetime, Field, model_validator

from contracts.schemas.base import CONTRACT_VERSION, ContractModel, JsonObject, NonBlankStr
from contracts.schemas.enums import (
    MemoryKind,
    MemoryStatus,
    MemorySubtype,
    PreferencePolarity,
    PreferenceScope,
    Source,
)


class Envelope(ContractModel):
    contract_version: str = Field(default=CONTRACT_VERSION, pattern=r"^1\.0$")
    request_id: NonBlankStr
    idempotency_key: NonBlankStr
    user_id: NonBlankStr
    session_id: NonBlankStr | None = None
    scene: NonBlankStr
    source: Source
    source_event_id: NonBlankStr
    occurred_at: AwareDatetime
    payload: JsonObject


class WriteContext(ContractModel):
    request_id: NonBlankStr
    idempotency_key: NonBlankStr
    user_id: NonBlankStr
    source_event_id: NonBlankStr


class EventBatch(ContractModel):
    events: list[Envelope] = Field(min_length=1)

    @model_validator(mode="after")
    def one_request_context(self) -> "EventBatch":
        if len({event.request_id for event in self.events}) != 1:
            raise ValueError("all events must use the same request_id")
        if len({event.user_id for event in self.events}) != 1:
            raise ValueError("all events must use the same user_id")
        return self
