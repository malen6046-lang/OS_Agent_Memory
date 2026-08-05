from typing import Generic, Literal, TypeVar

from pydantic import Field

from contracts.schemas.base import ContractModel, JsonObject, NonBlankStr
from contracts.schemas.enums import ErrorCode, Provider


class ErrorBody(ContractModel):
    code: ErrorCode
    message: NonBlankStr
    retryable: bool
    details: JsonObject = Field(default_factory=dict)


class ResponseMeta(ContractModel):
    elapsed_ms: int = Field(strict=True, ge=0)
    degraded: bool = False
    provider: Provider | None = None


T = TypeVar("T")


class SuccessResponse(ContractModel, Generic[T]):
    success: Literal[True] = True
    request_id: NonBlankStr
    data: T
    meta: ResponseMeta


class ErrorResponse(ContractModel):
    success: Literal[False] = False
    request_id: NonBlankStr
    error: ErrorBody
    meta: ResponseMeta
