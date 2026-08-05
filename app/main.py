"""FastAPI application entry point for the V1.2.1 platform."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.api.v1.router import api_router
from app.core.config import ConfigManager
from app.core.database import create_session_factory, init_db
from app.core.errors import AppError
from app.core.responses import error, new_request_id
from app.dependencies import build_service_container, get_memory_orchestrator
from app.services.platform import MemoryApiService
from app.repositories import SqlAlchemyPlatformRepository
from contracts.schemas import ErrorCode

REQUEST_ID_HEADER = "X-Request-ID"


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Own the database and provider graph for the application lifetime."""

    config = ConfigManager().load()
    database_engine = init_db()
    repository = SqlAlchemyPlatformRepository(
        create_session_factory(database_engine)
    )
    container = build_service_container(config)
    orchestrator = get_memory_orchestrator(container)
    api_service = MemoryApiService(
        repository=repository,
        orchestrator=orchestrator,
        service_container=container,
    )

    await container.start()
    application.state.config = config
    application.state.database_engine = database_engine
    application.state.service_container = container
    application.state.memory_orchestrator = orchestrator
    application.state.api_service = api_service
    try:
        yield
    finally:
        await container.close()
        database_engine.dispose()


app = FastAPI(
    title="OS Agent Memory API",
    version="1.2.1",
    description="《模块接口规划 V1.2.1》FastAPI backend",
    lifespan=lifespan,
)
app.include_router(api_router)


def request_id_from(request: Request) -> str:
    return getattr(request.state, "request_id", None) or new_request_id()


@app.middleware("http")
async def attach_request_id(request: Request, call_next: Any):
    supplied_request_id = request.headers.get(REQUEST_ID_HEADER, "").strip()
    request.state.request_id = supplied_request_id or new_request_id()
    response = await call_next(request)
    response.headers[REQUEST_ID_HEADER] = request.state.request_id
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    payload = error(
        request_id=exc.request_id or request_id_from(request),
        code=exc.code,
        message=exc.message,
        retryable=exc.retryable,
        details=exc.details,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=payload.model_dump(mode="json"),
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    payload = error(
        request_id=request_id_from(request),
        code=ErrorCode.VALIDATION_ERROR,
        message="请求参数不符合接口契约",
        details={"errors": jsonable_encoder(exc.errors())},
    )
    return JSONResponse(status_code=422, content=payload.model_dump(mode="json"))


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "HTTP request failed"
    details = {} if isinstance(exc.detail, str) else {"detail": jsonable_encoder(exc.detail)}
    code = (
        ErrorCode.UNAUTHORIZED_SCOPE
        if exc.status_code == 403
        else ErrorCode.VALIDATION_ERROR
    )
    payload = error(
        request_id=request_id_from(request),
        code=code,
        message=message,
        details=details,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=payload.model_dump(mode="json"),
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, _exc: Exception) -> JSONResponse:
    payload = error(
        request_id=request_id_from(request),
        code=ErrorCode.INTERNAL_ERROR,
        message="服务内部错误",
    )
    return JSONResponse(status_code=500, content=payload.model_dump(mode="json"))
