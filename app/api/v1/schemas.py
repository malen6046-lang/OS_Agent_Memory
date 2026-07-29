"""Request-only models for API endpoints without frozen contract schemas."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints


NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class MemorySearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: NonEmptyString
    query: NonEmptyString
    top_k: int = Field(default=5, ge=1, le=100)
    filters: dict[str, JsonValue] = Field(default_factory=dict)


class ForgetPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: NonEmptyString
    memory_ids: list[NonEmptyString] = Field(min_length=1)
    reason: str | None = None


class ForgetExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: NonEmptyString
    plan_id: NonEmptyString
    confirmation_token: NonEmptyString


class EvaluationRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_names: list[NonEmptyString] = Field(min_length=1)
    dataset: dict[str, JsonValue] = Field(default_factory=dict)
