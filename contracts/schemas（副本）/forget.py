from pydantic import Field

from contracts.schemas.base import ContractModel, NonBlankStr
from contracts.schemas.common import WriteContext
from contracts.schemas.enums import ErrorCode, MemoryKind, RiskLevel


class ForgetPreviewRequest(ContractModel):
    request_id: NonBlankStr
    user_id: NonBlankStr
    instruction: NonBlankStr
    scene: NonBlankStr | None = None


class ForgetCandidate(ContractModel):
    memory_id: NonBlankStr
    content_text: NonBlankStr
    memory_kind: MemoryKind


class ForgetPlan(ContractModel):
    plan_id: NonBlankStr
    candidates: list[ForgetCandidate] = Field(default_factory=list)
    risk_level: RiskLevel
    confirmation_token: NonBlankStr


class ForgetExecuteRequest(WriteContext):
    confirmation_token: NonBlankStr
    selected_ids: list[NonBlankStr] = Field(min_length=1)


class ForgetFailedItem(ContractModel):
    memory_id: NonBlankStr
    code: ErrorCode
    message: NonBlankStr


class ForgetResult(ContractModel):
    plan_id: NonBlankStr
    requested_ids: list[NonBlankStr]
    tombstoned_ids: list[NonBlankStr]
    failed_items: list[ForgetFailedItem]
    audit_id: NonBlankStr
