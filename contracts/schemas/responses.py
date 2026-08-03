"""Unified success and error response contracts for V1.2.2."""

from __future__ import annotations

from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from .common import NonEmptyString


ResponseData = TypeVar("ResponseData")


class ErrorCode(str, Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHORIZED_SCOPE = "UNAUTHORIZED_SCOPE"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    MEMORY_CONFLICT_PENDING = "MEMORY_CONFLICT_PENDING"
    EMBEDDING_DIMENSION_MISMATCH = "EMBEDDING_DIMENSION_MISMATCH"
    EMBEDDING_PROVIDER_UNAVAILABLE = "EMBEDDING_PROVIDER_UNAVAILABLE"
    VECTOR_PROVIDER_UNAVAILABLE = "VECTOR_PROVIDER_UNAVAILABLE"
    SEARCH_TIMEOUT = "SEARCH_TIMEOUT"
    SENSITIVE_CONTENT_BLOCKED = "SENSITIVE_CONTENT_BLOCKED"
    CONFIRMATION_EXPIRED = "CONFIRMATION_EXPIRED"
    STORAGE_WRITE_FAILED = "STORAGE_WRITE_FAILED"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: ErrorCode | NonEmptyString
    message: NonEmptyString
    retryable: bool = False
    details: dict[str, JsonValue] = Field(default_factory=dict)


class ResponseMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    elapsed_ms: int = Field(default=0, ge=0)
    degraded: bool = False
    provider: NonEmptyString | None = None
    degradation_reason: NonEmptyString | None = None
    idempotent_replay: bool = False


class ApiResponse(BaseModel, Generic[ResponseData]):
    model_config = ConfigDict(extra="forbid")

    success: bool
    request_id: NonEmptyString
    data: ResponseData | None = None
    error: ErrorDetail | None = None
    meta: ResponseMeta = Field(default_factory=ResponseMeta)

    @model_validator(mode="after")
    def validate_success_error_pair(self) -> "ApiResponse[ResponseData]":
        if self.success and self.error is not None:
            raise ValueError("successful responses cannot contain an error")
        if not self.success and self.error is None:
            raise ValueError("failed responses must contain an error")
        return self


AnyApiResponse = ApiResponse[Any]
