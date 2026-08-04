"""Two-stage forget contracts for V1.2.2."""

from datetime import datetime
from typing import Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from .common import NonEmptyString


class ForgetPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: NonEmptyString
    user_id: NonEmptyString
    instruction: NonEmptyString | None = None
    memory_ids: list[NonEmptyString] = Field(default_factory=list)
    reason: str | None = None

    @model_validator(mode="after")
    def require_instruction_or_ids(self) -> "ForgetPreviewRequest":
        if self.instruction is None and not self.memory_ids:
            raise ValueError("instruction or memory_ids is required")
        return self


class ForgetCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: NonEmptyString
    user_id: NonEmptyString
    risk_level: Literal["low", "medium", "high"] = "low"


class ForgetPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: NonEmptyString
    user_id: NonEmptyString
    candidates: list[ForgetCandidate] = Field(default_factory=list)
    risk_level: Literal["low", "medium", "high"]
    confirmation_token: NonEmptyString
    expires_at: AwareDatetime
    requires_confirmation: bool = True


class ForgetExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: NonEmptyString
    user_id: NonEmptyString
    plan_id: NonEmptyString
    confirmation_token: NonEmptyString
    selected_ids: list[NonEmptyString] = Field(min_length=1)


class ForgetExecutionPlan(BaseModel):
    """Validated delete intent; this object performs no mutation."""

    model_config = ConfigDict(extra="forbid")

    request_id: NonEmptyString
    user_id: NonEmptyString
    plan_id: NonEmptyString
    memory_ids: list[NonEmptyString] = Field(min_length=1)
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def require_unexpired_plan(self) -> "ForgetExecutionPlan":
        if self.expires_at <= datetime.now(self.expires_at.tzinfo):
            raise ValueError("forget execution plan has expired")
        return self


class ForgetResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: NonEmptyString
    user_id: NonEmptyString
    memory_ids: list[NonEmptyString]
    vector_pks: list[int]
    status: Literal["executed", "partial_failed"]
