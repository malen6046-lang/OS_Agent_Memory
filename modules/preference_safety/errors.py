"""Stable, non-sensitive failures raised by the forget planner."""

from __future__ import annotations

from typing import ClassVar

from contracts.schemas.responses import ErrorCode


class ForgetServiceError(ValueError):
    """Base class for validation failures at the forget boundary."""

    error_code: ClassVar[ErrorCode] = ErrorCode.VALIDATION_ERROR


class ConfirmationInvalidError(ForgetServiceError):
    """The confirmation token does not identify the requested plan."""


class ConfirmationExpiredError(ForgetServiceError):
    """The confirmation token is no longer valid."""

    error_code = ErrorCode.CONFIRMATION_EXPIRED


class ForgetAuthorizationError(ForgetServiceError):
    """A caller tried to use a plan owned by another user."""

    error_code = ErrorCode.UNAUTHORIZED_SCOPE


class ForgetSelectionError(ForgetServiceError):
    """The execute selection is not a subset of previewed candidates."""
