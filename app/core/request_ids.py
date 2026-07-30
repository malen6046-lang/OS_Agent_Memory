from contracts.schemas import ErrorCode

from app.core.errors import AppError


def validate_request_id(header_request_id: str | None, body_request_id: str) -> str:
    if header_request_id is not None and header_request_id != body_request_id:
        raise AppError(
            code=ErrorCode.VALIDATION_ERROR,
            message="X-Request-ID与请求体request_id不一致",
            status_code=422,
            retryable=False,
            details={
                "header_request_id": header_request_id,
                "body_request_id": body_request_id,
            },
            request_id=body_request_id,
        )
    return body_request_id
