"""HTTP helpers backed by the frozen V1.2.2 response contract."""

from __future__ import annotations

from typing import Any, TypeVar
from uuid import uuid4

from pydantic import JsonValue

from contracts.schemas.responses import (
    ApiResponse,
    ErrorDetail,
    ResponseMeta,
)


ResponseData = TypeVar("ResponseData")
ApiError = ErrorDetail


def new_request_id() -> str:
    return f"req_{uuid4().hex}"


def success_response(
    request_id: str,
    data: ResponseData,
    *,
    meta: ResponseMeta | None = None,
) -> ApiResponse[ResponseData]:
    return ApiResponse(
        success=True,
        request_id=request_id,
        data=data,
        meta=meta or ResponseMeta(),
    )


def error_response(
    request_id: str,
    code: str,
    message: str,
    details: dict[str, JsonValue] | None = None,
    *,
    retryable: bool = False,
    meta: ResponseMeta | None = None,
) -> ApiResponse[Any]:
    return ApiResponse(
        success=False,
        request_id=request_id,
        error=ErrorDetail(
            code=code,
            message=message,
            retryable=retryable,
            details=details or {},
        ),
        meta=meta or ResponseMeta(),
    )


__all__ = [
    "ApiError",
    "ApiResponse",
    "ResponseMeta",
    "error_response",
    "new_request_id",
    "success_response",
]
