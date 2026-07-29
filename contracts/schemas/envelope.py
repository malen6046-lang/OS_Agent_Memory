"""Public ingestion envelope from Module Interface Plan V1.2."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, JsonValue

from .common import NonEmptyString, Source


class Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["1.0"]
    request_id: NonEmptyString
    idempotency_key: NonEmptyString
    user_id: NonEmptyString
    session_id: NonEmptyString | None = None
    scene: NonEmptyString
    source: Source
    source_event_id: NonEmptyString
    occurred_at: AwareDatetime
    payload: dict[str, JsonValue]
