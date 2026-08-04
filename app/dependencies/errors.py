"""Errors raised while assembling or managing application services."""


class ServiceStartupError(RuntimeError):
    """A configured service cannot be created or started."""


class ServiceLifecycleError(RuntimeError):
    """A provider cannot be closed cleanly."""


class OrchestratorResponseError(RuntimeError):
    """A failed Orchestrator response awaiting HTTP error mapping."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}
