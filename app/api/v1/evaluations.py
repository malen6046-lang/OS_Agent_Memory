"""Evaluation execution endpoint."""

from typing import Any

from fastapi import APIRouter, Depends

from app.api.dependencies import get_mock_service, get_request_id
from app.api.mock_service import MockService
from app.core.responses import ApiResponse, success_response

from .schemas import EvaluationRunRequest


router = APIRouter(prefix="/evaluations", tags=["evaluations"])


@router.post("/run", response_model=ApiResponse[dict[str, Any]])
async def run_evaluation(
    evaluation_request: EvaluationRunRequest,
    request_id: str = Depends(get_request_id),
    service: MockService = Depends(get_mock_service),
) -> ApiResponse[dict[str, Any]]:
    return success_response(
        request_id, await service.run_evaluation(evaluation_request)
    )
