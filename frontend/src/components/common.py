"""Shared Streamlit rendering, state, and error handling."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import asdict
from typing import Any
from uuid import uuid4

import streamlit as st

from src.api.client import MemoryApiClient
from src.types.models import ApiClientError, ApiError, ApiResult


ERROR_HINTS = {
    "VALIDATION_ERROR": "请检查必填项、数值范围和输入格式。",
    "HTTP_422": "提交内容未通过校验，请检查表单字段。",
    "HTTP_404": "请求的接口不存在，请确认 FastAPI 地址包含 /api/v1。",
    "HTTP_500": "后端发生内部错误，请使用 request_id 查询日志。",
    "HTTP_503": "后端服务尚未就绪，请检查系统状态后重试。",
    "UNAUTHORIZED_SCOPE": "当前用户无权访问该记忆，请检查 user_id。",
    "IDEMPOTENCY_CONFLICT": "该幂等键已用于不同请求，请生成新的幂等键。",
    "MEMORY_CONFLICT_PENDING": "记忆冲突仍待处理，请稍后重试或人工审核。",
    "EMBEDDING_DIMENSION_MISMATCH": "向量维度不一致，请检查模型和索引配置。",
    "SENSITIVE_CONTENT_BLOCKED": "内容被安全策略拦截，请移除敏感内容后重试。",
    "SEARCH_TIMEOUT": "检索超时，请缩小结果数量或稍后重试。",
    "DEPENDENCY_UNAVAILABLE": "后端依赖暂时不可用，请检查健康状态。",
    "VECTOR_PROVIDER_UNAVAILABLE": "向量服务不可用，请检查 provider 状态。",
    "EMBEDDING_PROVIDER_UNAVAILABLE": "向量化服务不可用，请检查模型状态。",
    "CONFIRMATION_EXPIRED": "确认令牌已过期，请重新执行遗忘预览。",
    "STORAGE_WRITE_FAILED": "记忆写入失败，请确认存储服务可用。",
    "INTERNAL_ERROR": "后端发生内部错误，请使用 request_id 查询日志。",
}


def initialize_session() -> None:
    defaults: dict[str, Any] = {
        "api_base_url": os.getenv(
            "OS_AGENT_MEMORY_API_URL",
            "http://127.0.0.1:8000/api/v1",
        ),
        "api_timeout_seconds": 5.0,
        "active_user_id": "usr_demo",
        "request_history": [],
        "known_memory_ids": [],
        "search_memory_ids": [],
        "last_health_result": None,
        "last_ingest_result": None,
        "last_search_result": None,
        "last_preview_result": None,
        "last_execute_result": None,
        "forget_plan": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def api_client() -> MemoryApiClient:
    return MemoryApiClient(
        st.session_state.api_base_url,
        timeout_seconds=float(st.session_state.api_timeout_seconds),
    )


def new_request_id() -> str:
    return f"req_ui_{uuid4().hex}"


def new_event_id() -> str:
    return f"evt_ui_{uuid4().hex}"


def new_idempotency_key() -> str:
    return f"idem_ui_{uuid4().hex}"


def perform_api_call(
    operation: str,
    call: Callable[[MemoryApiClient], ApiResult],
) -> ApiResult | None:
    try:
        with st.spinner(f"正在执行：{operation}…"):
            result = call(api_client())
    except ValueError as exc:
        st.error(f"API 配置错误：{exc}")
        _record_transport_error(operation, str(exc), None)
        return None
    except ApiClientError as exc:
        st.error(str(exc))
        if exc.request_id:
            st.caption(f"request_id：`{exc.request_id}`")
        _record_transport_error(operation, str(exc), exc.request_id)
        return None

    _record_result(operation, result)
    return result


def render_api_result(
    result: ApiResult,
    *,
    success_message: str,
    show_payload: bool = True,
) -> bool:
    if result.success:
        st.success(success_message)
    else:
        st.error(friendly_error_message(result.error))
        if result.error and result.error.retryable:
            st.info("该错误允许重试。请先检查系统状态，再重新提交。")

    render_response_meta(result)
    if show_payload:
        with st.expander("查看完整 API 响应", expanded=not result.success):
            st.json(
                {
                    "success": result.success,
                    "request_id": result.request_id,
                    "data": result.data,
                    "error": asdict(result.error) if result.error else None,
                    "meta": asdict(result.meta),
                    "http_status": result.http_status,
                }
            )
    return result.success


def render_response_meta(result: ApiResult) -> None:
    st.caption("request_id")
    st.code(result.request_id)
    degraded_column, elapsed_column = st.columns(2)
    degraded_column.metric(
        "运行模式",
        "降级" if result.meta.degraded else "正常",
    )
    elapsed_column.metric("响应耗时", f"{result.meta.elapsed_ms} ms")

    if result.meta.degraded:
        reason = result.meta.degradation_reason or "后端未提供降级原因"
        st.warning(f"本次请求处于 degraded 模式：{reason}")
    if result.meta.idempotent_replay:
        st.info("本次结果来自幂等回放，没有重复执行写入。")
    if result.meta.provider:
        st.caption(f"provider：`{result.meta.provider}`")


def friendly_error_message(error: ApiError | None) -> str:
    if error is None:
        return "请求失败，但后端没有提供错误详情。"
    normalized = error.code.strip().upper()
    hint = ERROR_HINTS.get(normalized, "请根据提示检查输入，或联系后端维护者。")
    return f"{error.message}（{error.code}）\n\n{hint}"


def remember_memory_ids(memory_ids: list[str]) -> None:
    current = list(st.session_state.known_memory_ids)
    for memory_id in memory_ids:
        if memory_id and memory_id not in current:
            current.append(memory_id)
    st.session_state.known_memory_ids = current


def forget_memory_ids(memory_ids: list[str]) -> None:
    removed = set(memory_ids)
    st.session_state.known_memory_ids = [
        item for item in st.session_state.known_memory_ids if item not in removed
    ]
    st.session_state.search_memory_ids = [
        item for item in st.session_state.search_memory_ids if item not in removed
    ]


def render_request_history() -> None:
    history = st.session_state.request_history
    if not history:
        st.caption("当前会话还没有 API 请求。")
        return
    for item in reversed(history[-6:]):
        icon = "✅" if item["success"] else "❌"
        request_id = item.get("request_id") or "无 request_id"
        st.caption(f"{icon} {item['operation']} · {request_id}")


def _record_result(operation: str, result: ApiResult) -> None:
    history = list(st.session_state.request_history)
    history.append(
        {
            "operation": operation,
            "success": result.success,
            "request_id": result.request_id,
            "degraded": result.meta.degraded,
            "http_status": result.http_status,
        }
    )
    st.session_state.request_history = history[-20:]


def _record_transport_error(
    operation: str,
    message: str,
    request_id: str | None,
) -> None:
    history = list(st.session_state.request_history)
    history.append(
        {
            "operation": operation,
            "success": False,
            "request_id": request_id,
            "degraded": False,
            "http_status": None,
            "message": message,
        }
    )
    st.session_state.request_history = history[-20:]
