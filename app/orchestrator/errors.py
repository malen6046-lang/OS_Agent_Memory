"""Stable orchestration errors mapped from collaborator failures."""

from __future__ import annotations

from typing import Any


class OrchestratorError(RuntimeError):
    """Project-level error without leaking implementation exceptions."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}


class DependencyUnavailableError(OrchestratorError):
    def __init__(self, dependency: str, operation: str) -> None:
        super().__init__(
            "DEPENDENCY_UNAVAILABLE",
            f"{dependency} is unavailable",
            retryable=True,
            details={"dependency": dependency, "operation": operation},
        )


class OrchestratorTimeoutError(OrchestratorError):
    def __init__(
        self,
        dependency: str,
        operation: str,
        *,
        code: str = "DEPENDENCY_UNAVAILABLE",
    ) -> None:
        super().__init__(
            code,
            f"{dependency} timed out",
            retryable=True,
            details={"dependency": dependency, "operation": operation},
        )


class ValidationOrchestratorError(OrchestratorError):
    def __init__(self, message: str = "Request validation failed") -> None:
        super().__init__("VALIDATION_ERROR", message)


class SensitiveContentBlockedError(OrchestratorError):
    def __init__(self) -> None:
        super().__init__(
            "SENSITIVE_CONTENT_BLOCKED",
            "Sensitive content policy rejected the write",
        )


class IdempotencyConflictError(OrchestratorError):
    def __init__(self) -> None:
        super().__init__(
            "IDEMPOTENCY_CONFLICT",
            "The idempotency key was used for a different request",
        )
