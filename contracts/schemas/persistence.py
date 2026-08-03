"""Repository command/result objects used by the Orchestrator."""

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from .common import NonEmptyString
from .forget import ForgetExecutionPlan
from .knowledge import IngestResult
from .memory import MemoryRecord
from .preference import PreferenceRecord
from .provider import VectorItem


class IdempotencyEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: NonEmptyString
    operation: NonEmptyString
    idempotency_key: NonEmptyString
    fingerprint: NonEmptyString
    response: dict[str, JsonValue]


class IngestServiceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferences: list[PreferenceRecord] = Field(default_factory=list)
    knowledge: IngestResult


class IngestCommitResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: list[MemoryRecord] = Field(default_factory=list)
    vector_items: list[VectorItem] = Field(default_factory=list)


class LogicalDeleteResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: NonEmptyString
    user_id: NonEmptyString
    memory_ids: list[NonEmptyString] = Field(min_length=1)
    vector_pks: list[int] = Field(min_length=1)


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: NonEmptyString
    request_id: NonEmptyString
    user_id: NonEmptyString
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class AuditResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_id: NonEmptyString


ForgetDeleteCommand = ForgetExecutionPlan
