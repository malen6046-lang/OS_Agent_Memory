"""Typed view of the frozen FastAPI response envelope."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ApiError:
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResponseMeta:
    elapsed_ms: int = 0
    degraded: bool = False
    provider: str | None = None
    degradation_reason: str | None = None
    idempotent_replay: bool = False


@dataclass(frozen=True)
class ApiResult:
    success: bool
    request_id: str
    data: Any = None
    error: ApiError | None = None
    meta: ResponseMeta = field(default_factory=ResponseMeta)
    http_status: int = 200


class ApiClientError(RuntimeError):
    """The API could not be reached or returned a non-contract response."""

    def __init__(self, message: str, *, request_id: str | None = None) -> None:
        super().__init__(message)
        self.request_id = request_id
