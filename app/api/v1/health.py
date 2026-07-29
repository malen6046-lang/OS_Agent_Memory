"""Health endpoint."""

from typing import Any

from fastapi import APIRouter, Depends

from app.api.dependencies import get_mock_service, get_request_id
from app.api.mock_service import MockService
from app.core.responses import ApiResponse, success_response


router = APIRouter(tags=["health"])


@router.get("/health", response_model=ApiResponse[dict[str, Any]])
async def health(
    request_id: str = Depends(get_request_id),
    service: MockService = Depends(get_mock_service),
) -> ApiResponse[dict[str, Any]]:
    return success_response(request_id, await service.health())
