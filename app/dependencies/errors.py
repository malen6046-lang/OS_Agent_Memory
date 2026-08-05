"""Errors raised while assembling or managing application services."""


class ServiceStartupError(RuntimeError):
    """A configured service cannot be created or started."""


class ServiceLifecycleError(RuntimeError):
    """A provider cannot be closed cleanly."""
