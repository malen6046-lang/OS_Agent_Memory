"""Safety decision contract for ingestion pre-checks."""

from pydantic import BaseModel, ConfigDict, Field

from .common import NonEmptyString


class SafetyCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed: bool
    reason_codes: list[NonEmptyString] = Field(default_factory=list)
    entity_types: list[NonEmptyString] = Field(default_factory=list)

