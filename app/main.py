from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.errors import AppError
from contracts.schemas import ErrorBody, ErrorCode, ErrorResponse, ResponseMeta


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 后续在此统一启动/关闭 repository、EmbeddingProvider 和 VectorStoreAdapter。
    yield


app = FastAPI(
    title="OS Agent Memory API",
    version="1.0.0",
    description="《模块接口规划 V1.1》FastAPI 后端骨架",
    lifespan=lifespan,
)
app.include_router(api_router)


def request_id_from(request: Request) -> str:
    return request.headers.get("X-Request-ID") or f"req_{uuid4()}"


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    payload = ErrorResponse(
        request_id=exc.request_id or request_id_from(request),
        error=ErrorBody(
            code=exc.code,
            message=exc.message,
            retryable=exc.retryable,
            details=exc.details,
        ),
        meta=ResponseMeta(elapsed_ms=0, degraded=False),
    )
    return JSONResponse(status_code=exc.status_code, content=payload.model_dump(mode="json"))


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    payload = ErrorResponse(
        request_id=request_id_from(request),
        error=ErrorBody(
            code=ErrorCode.VALIDATION_ERROR,
            message="请求参数不符合接口契约",
            retryable=False,
            details={"errors": jsonable_encoder(exc.errors())},
        ),
        meta=ResponseMeta(elapsed_ms=0, degraded=False),
    )
    return JSONResponse(status_code=422, content=payload.model_dump(mode="json"))


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    payload = ErrorResponse(
        request_id=request_id_from(request),
        error=ErrorBody(
            code=ErrorCode.INTERNAL_ERROR,
            message="服务内部错误",
            retryable=False,
            details={},
        ),
        meta=ResponseMeta(elapsed_ms=0, degraded=False),
    )
    return JSONResponse(status_code=500, content=payload.model_dump(mode="json"))
