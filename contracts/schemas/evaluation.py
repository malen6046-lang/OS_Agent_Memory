"""Evaluation-run contracts for V1.2.2."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue

from .common import NonEmptyString


class EvaluationRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: NonEmptyString
    metric_names: list[NonEmptyString] = Field(min_length=1)
    dataset: dict[str, JsonValue] = Field(default_factory=dict)


class EvaluationRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: NonEmptyString
    request_id: NonEmptyString
    status: Literal["accepted", "running", "completed", "failed"]
    metrics: dict[str, float] = Field(default_factory=dict)
    created_at: AwareDatetime
