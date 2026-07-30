from pydantic import AwareDatetime, Field

from contracts.schemas.base import ContractModel, JsonObject, NonBlankStr
from contracts.schemas.enums import EvaluationStatus, EvaluationType
from contracts.schemas.responses import ErrorBody


class EvaluationRunRequest(ContractModel):
    request_id: NonBlankStr
    user_id: NonBlankStr
    evaluation_types: list[EvaluationType] = Field(min_length=1)
    attributes: JsonObject = Field(default_factory=dict)


class EvaluationResult(ContractModel):
    evaluation_run_id: NonBlankStr
    status: EvaluationStatus
    evaluation_types: list[EvaluationType] = Field(min_length=1)
    created_at: AwareDatetime
    started_at: AwareDatetime | None = None
    completed_at: AwareDatetime | None = None
    report_uri: NonBlankStr | None = None
    metrics: JsonObject | None = None
    error: ErrorBody | None = None
