"""Two-stage forget Protocol frozen by CR-20260803-001."""

from typing import Protocol

from contracts.schemas.forget import (
    ForgetExecuteRequest,
    ForgetExecutionPlan,
    ForgetPlan,
    ForgetPreviewRequest,
)


class ForgetService(Protocol):
    def preview(self, request: ForgetPreviewRequest) -> ForgetPlan: ...

    def execute(
        self, request: ForgetExecuteRequest
    ) -> ForgetExecutionPlan: ...
