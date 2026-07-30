from fastapi import APIRouter

from app.api.v1.routes import router as routes_router
from contracts.schemas import ErrorResponse

api_router = APIRouter(
    prefix="/api/v1",
    responses={
        422: {"model": ErrorResponse, "description": "请求或业务校验失败"},
        500: {"model": ErrorResponse, "description": "服务内部错误"},
    },
)
api_router.include_router(routes_router)
