"""Forget preview and execution endpoints."""

from typing import Any

from fastapi import APIRouter, Depends

from app.api.dependencies import get_mock_service, get_request_id
from app.api.mock_service import MockService
from app.core.responses import ApiResponse, success_response

from .schemas import ForgetExecuteRequest, ForgetPreviewRequest


router = APIRouter(prefix="/forget", tags=["forget"])


@router.post("/preview", response_model=ApiResponse[dict[str, Any]])
async def preview_forget(
    preview_request: ForgetPreviewRequest,
    request_id: str = Depends(get_request_id),
    service: MockService = Depends(get_mock_service),
) -> ApiResponse[dict[str, Any]]:
    return success_response(
        request_id,
        await service.preview_forget(preview_request, request_id=request_id),
    )


@router.post("/execute", response_model=ApiResponse[dict[str, Any]])
async def execute_forget(
    execute_request: ForgetExecuteRequest,
    request_id: str = Depends(get_request_id),
    service: MockService = Depends(get_mock_service),
) -> ApiResponse[dict[str, Any]]:
    return success_response(
        request_id,
        await service.execute_forget(execute_request, request_id=request_id),
    )
