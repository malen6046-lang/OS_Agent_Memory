import httpx
import pytest

from src.api.client import MemoryApiClient
from src.components.common import ERROR_HINTS, friendly_error_message
from src.types.models import ApiClientError, ApiError


def test_health_parses_unified_success_response():
    def handler(request):
        assert request.method == "GET"
        assert request.url.path == "/api/v1/health"
        return httpx.Response(
            200,
            json={
                "success": True,
                "request_id": "req_health",
                "data": {"status": "ok"},
                "error": None,
                "meta": {
                    "elapsed_ms": 12,
                    "degraded": True,
                    "provider": "fallback",
                    "degradation_reason": "primary unavailable",
                    "idempotent_replay": False,
                },
            },
        )

    result = MemoryApiClient(
        "http://api.test/api/v1",
        transport=httpx.MockTransport(handler),
    ).health(request_id="req_health")

    assert result.success is True
    assert result.request_id == "req_health"
    assert result.meta.degraded is True
    assert result.meta.provider == "fallback"


def test_search_posts_only_to_public_fastapi_endpoint():
    def handler(request):
        assert request.method == "POST"
        assert request.url.path == "/api/v1/memory/search"
        assert request.headers["X-Request-ID"] == "req_search"
        return httpx.Response(
            200,
            json={
                "success": True,
                "request_id": "req_search",
                "data": {"items": []},
                "error": None,
                "meta": {},
            },
        )

    result = MemoryApiClient(
        "http://api.test/api/v1/",
        transport=httpx.MockTransport(handler),
    ).search(
        {"user_id": "usr_1", "query": "release", "top_k": 5},
        request_id="req_search",
    )

    assert result.success is True


@pytest.mark.parametrize(
    ("method_name", "expected_path"),
    [
        ("ingest", "/api/v1/events/ingest"),
        ("preview_forget", "/api/v1/forget/preview"),
        ("execute_forget", "/api/v1/forget/execute"),
    ],
)
def test_mutating_actions_use_only_public_fastapi_endpoints(
    method_name,
    expected_path,
):
    def handler(request):
        assert request.method == "POST"
        assert request.url.path == expected_path
        return httpx.Response(
            200,
            json={
                "success": True,
                "request_id": "req_action",
                "data": {},
                "error": None,
                "meta": {},
            },
        )

    client = MemoryApiClient(
        "http://api.test/api/v1",
        transport=httpx.MockTransport(handler),
    )
    result = getattr(client, method_name)({}, request_id="req_action")

    assert result.success is True


def test_unified_error_is_parsed_and_has_friendly_hint():
    def handler(_request):
        return httpx.Response(
            503,
            json={
                "success": False,
                "request_id": "req_error",
                "data": None,
                "error": {
                    "code": "DEPENDENCY_UNAVAILABLE",
                    "message": "retriever is unavailable",
                    "retryable": True,
                    "details": {"dependency": "retriever"},
                },
                "meta": {"degraded": False},
            },
        )

    result = MemoryApiClient(
        "http://api.test/api/v1",
        transport=httpx.MockTransport(handler),
    ).health()

    assert result.success is False
    assert result.http_status == 503
    assert result.error.retryable is True
    assert "后端依赖暂时不可用" in friendly_error_message(result.error)


@pytest.mark.parametrize("error_code", sorted(ERROR_HINTS))
def test_every_known_api_error_has_a_chinese_action_hint(error_code):
    message = friendly_error_message(
        ApiError(code=error_code, message="request failed")
    )

    assert ERROR_HINTS[error_code] in message
    assert "request failed" in message


def test_non_contract_response_is_rejected():
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(200, json={"status": "ok"})
    )

    with pytest.raises(ApiClientError, match="success"):
        MemoryApiClient(
            "http://api.test/api/v1",
            transport=transport,
        ).health()


def test_connection_error_has_readable_message():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(ApiClientError, match="无法连接 FastAPI"):
        MemoryApiClient(
            "http://api.test/api/v1",
            transport=httpx.MockTransport(handler),
        ).health()


@pytest.mark.parametrize(
    "base_url",
    ["", "localhost:8000/api/v1", "file:///tmp/memory.db"],
)
def test_client_rejects_non_http_api_address(base_url):
    with pytest.raises(ValueError, match="API 地址"):
        MemoryApiClient(base_url)
