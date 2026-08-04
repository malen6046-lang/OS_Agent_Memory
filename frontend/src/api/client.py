"""HTTP client for the public OS Agent Memory FastAPI endpoints only."""

from __future__ import annotations

from typing import Any

import httpx

from src.types.models import ApiClientError, ApiError, ApiResult, ResponseMeta


class MemoryApiClient:
    """Small synchronous client suitable for Streamlit's rerun model."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 5.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        normalized = base_url.strip().rstrip("/")
        try:
            parsed = httpx.URL(normalized)
        except Exception as exc:
            raise ValueError("API 地址格式无效") from exc
        if parsed.scheme not in {"http", "https"} or not parsed.host:
            raise ValueError("API 地址必须是 http:// 或 https:// 地址")
        if timeout_seconds <= 0:
            raise ValueError("请求超时时间必须大于 0")

        self._base_url = normalized
        self._timeout = timeout_seconds
        self._transport = transport

    def health(self, *, request_id: str | None = None) -> ApiResult:
        return self._request("GET", "/health", request_id=request_id)

    def ingest(
        self,
        payload: dict[str, Any],
        *,
        request_id: str | None = None,
    ) -> ApiResult:
        return self._request(
            "POST",
            "/events/ingest",
            payload=payload,
            request_id=request_id,
        )

    def search(
        self,
        payload: dict[str, Any],
        *,
        request_id: str | None = None,
    ) -> ApiResult:
        return self._request(
            "POST",
            "/memory/search",
            payload=payload,
            request_id=request_id,
        )

    def preview_forget(
        self,
        payload: dict[str, Any],
        *,
        request_id: str | None = None,
    ) -> ApiResult:
        return self._request(
            "POST",
            "/forget/preview",
            payload=payload,
            request_id=request_id,
        )

    def execute_forget(
        self,
        payload: dict[str, Any],
        *,
        request_id: str | None = None,
    ) -> ApiResult:
        return self._request(
            "POST",
            "/forget/execute",
            payload=payload,
            request_id=request_id,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> ApiResult:
        headers = {"Accept": "application/json"}
        if request_id:
            headers["X-Request-ID"] = request_id

        try:
            with httpx.Client(
                base_url=self._base_url,
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = client.request(
                    method,
                    path,
                    json=payload,
                    headers=headers,
                )
        except httpx.TimeoutException as exc:
            raise ApiClientError(
                "请求超时，请确认后端正在运行，或稍后重试。",
                request_id=request_id,
            ) from exc
        except httpx.RequestError as exc:
            raise ApiClientError(
                "无法连接 FastAPI 服务，请检查 API 地址和后端进程。",
                request_id=request_id,
            ) from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise ApiClientError(
                f"后端返回了非 JSON 响应（HTTP {response.status_code}）。",
                request_id=request_id,
            ) from exc
        if not isinstance(body, dict):
            raise ApiClientError(
                "后端响应格式不正确：根节点不是对象。",
                request_id=request_id,
            )

        return _parse_result(body, response.status_code, request_id)


def _parse_result(
    body: dict[str, Any],
    status_code: int,
    fallback_request_id: str | None,
) -> ApiResult:
    success = body.get("success")
    response_request_id = body.get("request_id")
    if not isinstance(success, bool):
        raise ApiClientError(
            "后端响应缺少布尔类型 success 字段。",
            request_id=fallback_request_id,
        )
    if not isinstance(response_request_id, str) or not response_request_id.strip():
        raise ApiClientError(
            "后端响应缺少有效 request_id。",
            request_id=fallback_request_id,
        )

    meta_data = body.get("meta") or {}
    if not isinstance(meta_data, dict):
        raise ApiClientError(
            "后端响应中的 meta 格式不正确。",
            request_id=response_request_id,
        )
    meta = ResponseMeta(
        elapsed_ms=_non_negative_int(meta_data.get("elapsed_ms", 0)),
        degraded=bool(meta_data.get("degraded", False)),
        provider=_optional_text(meta_data.get("provider")),
        degradation_reason=_optional_text(
            meta_data.get("degradation_reason")
        ),
        idempotent_replay=bool(
            meta_data.get("idempotent_replay", False)
        ),
    )

    error = None
    if not success:
        error_data = body.get("error")
        if not isinstance(error_data, dict):
            raise ApiClientError(
                "失败响应缺少统一 error 对象。",
                request_id=response_request_id,
            )
        details = error_data.get("details") or {}
        error = ApiError(
            code=str(error_data.get("code", "INTERNAL_ERROR")),
            message=str(error_data.get("message", "请求失败")),
            retryable=bool(error_data.get("retryable", False)),
            details=details if isinstance(details, dict) else {},
        )

    return ApiResult(
        success=success,
        request_id=response_request_id,
        data=body.get("data"),
        error=error,
        meta=meta,
        http_status=status_code,
    )


def _non_negative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _optional_text(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None
