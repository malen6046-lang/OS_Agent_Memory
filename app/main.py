"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.api import api_v1_router
from app.api.dependencies import get_mock_service
from app.core.config import ConfigManager
from app.core.responses import error_response, new_request_id
from app.dependencies import (
    OrchestratorApiService,
    OrchestratorResponseError,
    build_service_container,
    get_memory_orchestrator,
)


REQUEST_ID_HEADER = "X-Request-ID"


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Own one configured service graph for the application lifetime."""
    config = ConfigManager().load()
    container = build_service_container(config)
    orchestrator = get_memory_orchestrator(container)
    api_service = OrchestratorApiService(container, orchestrator)

    await container.start()
    application.state.config = config
    application.state.service_container = container
    application.state.memory_orchestrator = orchestrator
    application.state.api_service = api_service
    try:
        yield
    finally:
        await container.close()


app = FastAPI(
    title="OS Agent Memory System",
    version="1.0.0",
    lifespan=lifespan,
)


def get_lifecycle_api_service(request: Request) -> OrchestratorApiService:
    service = getattr(request.app.state, "api_service", None)
    if service is None:
        raise HTTPException(
            status_code=503,
            detail="Application services are not initialized",
        )
    return service


app.dependency_overrides[get_mock_service] = get_lifecycle_api_service


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or new_request_id()


@app.middleware("http")
async def attach_request_id(request: Request, call_next: Any):
    supplied_request_id = request.headers.get(REQUEST_ID_HEADER, "").strip()
    request.state.request_id = supplied_request_id or new_request_id()
    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = request.state.request_id
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    response = error_response(
        request_id=_request_id(request),
        code="validation_error",
        message="Request validation failed",
        details={"errors": jsonable_encoder(exc.errors())},
    )
    return JSONResponse(status_code=422, content=response.model_dump(mode="json"))


@app.exception_handler(OrchestratorResponseError)
async def orchestrator_exception_handler(
    request: Request, exc: OrchestratorResponseError
) -> JSONResponse:
    status_code = {
        "VALIDATION_ERROR": 422,
        "SENSITIVE_CONTENT_BLOCKED": 422,
        "IDEMPOTENCY_CONFLICT": 409,
        "CONFIRMATION_EXPIRED": 410,
        "SEARCH_TIMEOUT": 504,
        "DEPENDENCY_UNAVAILABLE": 503,
        "VECTOR_PROVIDER_UNAVAILABLE": 503,
        "EMBEDDING_PROVIDER_UNAVAILABLE": 503,
    }.get(exc.code, 500)
    response = error_response(
        request_id=_request_id(request),
        code=exc.code,
        message=exc.message,
        details=exc.details,
        retryable=exc.retryable,
    )
    return JSONResponse(
        status_code=status_code,
        content=response.model_dump(mode="json"),
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(
    request: Request, exc: HTTPException
) -> JSONResponse:
    if isinstance(exc.detail, str):
        message = exc.detail
        details = None
    else:
        message = "HTTP request failed"
        details = {"detail": jsonable_encoder(exc.detail)}
    response = error_response(
        request_id=_request_id(request),
        code=f"http_{exc.status_code}",
        message=message,
        details=details,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=response.model_dump(mode="json"),
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request, _exc: Exception
) -> JSONResponse:
    response = error_response(
        request_id=_request_id(request),
        code="internal_error",
        message="Internal server error",
    )
    return JSONResponse(status_code=500, content=response.model_dump(mode="json"))


app.include_router(api_v1_router, prefix="/api/v1")
