"""V1.2.1 unified success and error response builders."""

from __future__ import annotations

from time import perf_counter
from typing import TypeVar
from uuid import uuid4

from contracts.schemas import (
    ContractModel,
    ErrorBody,
    ErrorCode,
    ErrorResponse,
    JsonObject,
    Provider,
    ResponseMeta,
    SuccessResponse,
)

T = TypeVar("T", bound=ContractModel)


def new_request_id() -> str:
    return f"req_{uuid4()}"


def success(
    *,
    request_id: str,
    data: T,
    started_at: float,
    degraded: bool = False,
    provider: Provider | None = None,
) -> SuccessResponse[T]:
    elapsed_ms = max(0, round((perf_counter() - started_at) * 1000))
    return SuccessResponse(
        request_id=request_id,
        data=data,
        meta=ResponseMeta(
            elapsed_ms=elapsed_ms,
            degraded=degraded,
            provider=provider,
        ),
    )


def error(
    *,
    request_id: str,
    code: ErrorCode,
    message: str,
    retryable: bool = False,
    details: JsonObject | None = None,
    degraded: bool = False,
    provider: Provider | None = None,
    elapsed_ms: int = 0,
) -> ErrorResponse:
    return ErrorResponse(
        request_id=request_id,
        error=ErrorBody(
            code=code,
            message=message,
            retryable=retryable,
            details=details or {},
        ),
        meta=ResponseMeta(
            elapsed_ms=max(0, elapsed_ms),
            degraded=degraded,
            provider=provider,
        ),
    )
