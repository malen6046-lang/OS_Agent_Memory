"""Stable contract-facing failures raised by the forget adapter."""

from __future__ import annotations

from typing import ClassVar

from contracts.schemas.responses import ErrorCode


class ForgetAdapterError(ValueError):
    """Base class for safe forget validation failures."""

    error_code: ClassVar[ErrorCode] = ErrorCode.VALIDATION_ERROR


class ConfirmationInvalidError(ForgetAdapterError):
    """The token does not identify the requested plan."""


class ConfirmationExpiredError(ForgetAdapterError):
    """The confirmation window has elapsed."""

    error_code = ErrorCode.CONFIRMATION_EXPIRED


class ForgetAuthorizationError(ForgetAdapterError):
    """The caller does not own the confirmation plan."""

    error_code = ErrorCode.UNAUTHORIZED_SCOPE


class ForgetSelectionError(ForgetAdapterError):
    """The requested deletion exceeds the previewed candidates."""
