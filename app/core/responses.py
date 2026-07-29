"""Unified success and error response models for the HTTP API."""

from __future__ import annotations

from typing import Any, Generic, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, JsonValue, model_validator


ResponseData = TypeVar("ResponseData")


class ApiError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: dict[str, JsonValue] | None = None


class ApiResponse(BaseModel, Generic[ResponseData]):
    model_config = ConfigDict(extra="forbid")

    success: bool
    request_id: str
    data: ResponseData | None = None
    error: ApiError | None = None

    @model_validator(mode="after")
    def validate_success_error_pair(self) -> "ApiResponse[ResponseData]":
        if self.success and self.error is not None:
            raise ValueError("successful responses cannot contain an error")
        if not self.success and self.error is None:
            raise ValueError("failed responses must contain an error")
        return self


def new_request_id() -> str:
    return f"req_{uuid4().hex}"


def success_response(
    request_id: str, data: ResponseData
) -> ApiResponse[ResponseData]:
    return ApiResponse(success=True, request_id=request_id, data=data)


def error_response(
    request_id: str,
    code: str,
    message: str,
    details: dict[str, JsonValue] | None = None,
) -> ApiResponse[Any]:
    return ApiResponse(
        success=False,
        request_id=request_id,
        error=ApiError(code=code, message=message, details=details),
    )
