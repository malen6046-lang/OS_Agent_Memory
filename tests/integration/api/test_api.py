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
    assert set(body) == {
        "success",
        "request_id",
        "data",
        "error",
        "meta",
    }
    assert body["success"] is True
    assert body["request_id"]
    assert body["data"] is not None
    assert body["error"] is None
    assert body["meta"]["degraded"] is False
    assert body["meta"]["elapsed_ms"] >= 0
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
                "selected_ids": ["mem_1"],
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


def test_mock_api_import_search_forget_is_user_scoped(client):
    def ingest(user_id, event_id, content):
        response = client.post(
            "/api/v1/events/ingest",
            json={
                "contract_version": "1.0",
                "request_id": f"req_{event_id}",
                "idempotency_key": f"idem_{event_id}",
                "user_id": user_id,
                "session_id": None,
                "scene": "mvp_demo",
                "source": "tool_result",
                "source_event_id": event_id,
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "payload": {"content": content},
            },
        )
        body = assert_success_response(response)
        records = body["data"]["result"]["repository_result"]["records"]
        assert len(records) == 1
        return records[0]["memory_id"]

    first_memory_id = ingest(
        "usr_demo_1",
        "evt_demo_1",
        "Remember the release checklist and deployment notes.",
    )
    second_memory_id = ingest(
        "usr_demo_2",
        "evt_demo_2",
        "Private memory belonging to another user.",
    )

    first_search = assert_success_response(
        client.post(
            "/api/v1/memory/search",
            json={
                "user_id": "usr_demo_1",
                "query": "release checklist",
                "top_k": 5,
            },
        )
    )
    assert [
        item["memory_id"] for item in first_search["data"]["items"]
    ] == [first_memory_id]
    assert second_memory_id not in {
        item["memory_id"] for item in first_search["data"]["items"]
    }

    preview = assert_success_response(
        client.post(
            "/api/v1/forget/preview",
            json={
                "user_id": "usr_demo_1",
                "memory_ids": [first_memory_id],
                "reason": "MVP demonstration",
            },
        )
    )
    assert preview["data"]["affected_memory_ids"] == [first_memory_id]

    executed = assert_success_response(
        client.post(
            "/api/v1/forget/execute",
            json={
                "user_id": "usr_demo_1",
                "plan_id": preview["data"]["plan_id"],
                "confirmation_token": preview["data"][
                    "confirmation_token"
                ],
                "selected_ids": [first_memory_id],
            },
        )
    )
    assert executed["data"]["status"] == "executed"

    after_forget = assert_success_response(
        client.post(
            "/api/v1/memory/search",
            json={
                "user_id": "usr_demo_1",
                "query": "release checklist",
                "top_k": 5,
            },
        )
    )
    assert after_forget["data"]["items"] == []
