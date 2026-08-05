from datetime import datetime, timezone

import pytest


EXPECTED_ROUTES = {
    ("GET", "/api/v1/health"),
    ("POST", "/api/v1/events/ingest"),
    ("POST", "/api/v1/memory/search"),
    ("POST", "/api/v1/forget/preview"),
    ("POST", "/api/v1/forget/execute"),
    ("POST", "/api/v1/evaluations/run"),
}


def assert_success_response(response):
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"success", "request_id", "data", "error"}
    assert body["success"] is True
    assert body["request_id"]
    assert body["data"] is not None
    assert body["error"] is None
    assert response.headers["X-Request-ID"] == body["request_id"]
    return body


def test_all_required_routes_are_registered(client):
    paths = client.app.openapi()["paths"]
    registered = {
        (method.upper(), path)
        for path, operations in paths.items()
        for method in operations
        if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}
    }

    assert EXPECTED_ROUTES <= registered


def test_health_returns_unified_response_and_request_id(client):
    body = assert_success_response(client.get("/api/v1/health"))

    assert body["request_id"].startswith("req_")
    assert body["data"]["status"] == "ok"
    assert body["data"]["mock"] is True


def test_caller_request_id_is_preserved(client):
    response = client.get(
        "/api/v1/health", headers={"X-Request-ID": "req_caller_123"}
    )
    body = assert_success_response(response)

    assert body["request_id"] == "req_caller_123"


@pytest.mark.parametrize(
    ("path", "payload", "expected_key"),
    [
        (
            "/api/v1/events/ingest",
            {
                "contract_version": "1.0",
                "request_id": "req_event",
                "idempotency_key": "idem_event",
                "user_id": "usr_1",
                "session_id": None,
                "scene": "office_automation",
                "source": "tool_result",
                "source_event_id": "evt_1",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "payload": {"result": "ok"},
            },
            "accepted",
        ),
        (
            "/api/v1/memory/search",
            {
                "user_id": "usr_1",
                "query": "preferred output format",
                "top_k": 3,
            },
            "items",
        ),
        (
            "/api/v1/forget/preview",
            {
                "user_id": "usr_1",
                "memory_ids": ["mem_1"],
                "reason": "user request",
            },
            "plan_id",
        ),
        (
            "/api/v1/forget/execute",
            {
                "user_id": "usr_1",
                "plan_id": "forget_plan_1",
                "confirmation_token": "confirm_1",
            },
            "status",
        ),
        (
            "/api/v1/evaluations/run",
            {
                "metric_names": ["precision", "recall"],
                "dataset": {"name": "smoke"},
            },
            "run_id",
        ),
    ],
)
def test_post_endpoints_use_mock_service(
    client, path, payload, expected_key
):
    body = assert_success_response(client.post(path, json=payload))

    assert expected_key in body["data"]
    assert body["data"]["mock"] is True


def test_validation_error_uses_unified_error_response(client):
    response = client.post(
        "/api/v1/memory/search",
        json={"user_id": "usr_1", "top_k": 0},
        headers={"X-Request-ID": "req_invalid"},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["request_id"] == "req_invalid"
    assert body["data"] is None
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"]["errors"]


def test_not_found_uses_unified_error_response(client):
    response = client.get("/api/v1/not-found")

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["request_id"]
    assert body["data"] is None
    assert body["error"]["code"] == "http_404"
