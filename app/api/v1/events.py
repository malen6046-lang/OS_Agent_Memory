"""Event ingestion endpoint."""

from typing import Any

from fastapi import APIRouter, Depends

from app.api.dependencies import get_mock_service, get_request_id
from app.api.mock_service import MockService
from app.core.responses import ApiResponse, success_response
from contracts.schemas.envelope import Envelope


router = APIRouter(prefix="/events", tags=["events"])


@router.post("/ingest", response_model=ApiResponse[dict[str, Any]])
async def ingest_event(
    envelope: Envelope,
    request_id: str = Depends(get_request_id),
    service: MockService = Depends(get_mock_service),
) -> ApiResponse[dict[str, Any]]:
    return success_response(request_id, await service.ingest_event(envelope))
