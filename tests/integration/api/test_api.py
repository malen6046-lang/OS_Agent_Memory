"""V1.2.1 end-to-end HTTP API checks."""

from datetime import datetime, timezone

from app.main import app
from tests.asgi_client import ASGITestClient


def assert_success_response(response, expected_status: int = 200):
    assert response.status_code == expected_status, response.text
    body = response.json()
    assert set(body) == {"success", "request_id", "data", "meta"}
    assert body["success"] is True
    assert body["request_id"]
    assert body["meta"]["elapsed_ms"] >= 0
    return body


def test_health_returns_v121_envelope_and_request_id(client):
    response = client.get(
        "/api/v1/health", headers={"X-Request-ID": "req_caller_123"}
    )
    body = assert_success_response(response)
    assert body["request_id"] == "req_caller_123"
    assert body["data"]["contract_version"] == "1.0"


def test_openapi_contains_the_twelve_v121_paths(client):
    paths = set(client.get("/openapi.json").json()["paths"])
    frozen_paths = {
        "/api/v1/events/ingest",
        "/api/v1/preferences/extract",
        "/api/v1/preferences",
        "/api/v1/preferences/{key}/history",
        "/api/v1/knowledge/ingest",
        "/api/v1/memory/search",
        "/api/v1/conflicts/{conflict_id}/resolve",
        "/api/v1/forget/preview",
        "/api/v1/forget/execute",
        "/api/v1/memory/promotions/run",
        "/api/v1/health",
        "/api/v1/evaluations/run",
    }
    compatibility_paths = {
        "/api/v1/preferences/{key}/versions",
        "/api/v1/knowledge",
        "/api/v1/knowledge/conflicts/resolve",
        "/api/v1/memory/{memory_id}",
        "/api/v1/memory/transitions",
    }
    assert frozen_paths <= paths
    assert compatibility_paths <= paths


def test_validation_and_not_found_use_v121_error_envelope(client):
    validation = client.post(
        "/api/v1/memory/search",
        json={"request_id": "req_invalid", "user_id": "usr_1", "top_k": 0},
    )
    assert validation.status_code == 422
    validation_body = validation.json()
    assert set(validation_body) == {"success", "request_id", "error", "meta"}
    assert validation_body["error"]["code"] == "VALIDATION_ERROR"

    missing = client.get("/api/v1/not-found")
    assert missing.status_code == 404
    missing_body = missing.json()
    assert set(missing_body) == {"success", "request_id", "error", "meta"}


def test_real_algorithm_knowledge_write_then_search(monkeypatch):
    monkeypatch.setenv("OS_AGENT_ENV", "development")
    now = datetime.now(timezone.utc).isoformat()
    knowledge = {
        "request_id": "req_knowledge_e2e",
        "idempotency_key": "idem_knowledge_e2e",
        "user_id": "usr_e2e",
        "source_event_id": "evt_knowledge_e2e",
        "records": [
            {
                "title": "深色主题偏好",
                "knowledge_type": "fact",
                "body": "用户喜欢使用深色主题",
                "steps": [],
                "keywords": ["深色主题"],
                "source_uri": None,
                "source_reliability": 0.9,
                "effective_at": now,
            }
        ],
    }
    search = {
        "request_id": "req_search_e2e",
        "user_id": "usr_e2e",
        "query": "用户喜欢什么主题",
        "filters": {},
        "top_k": 5,
    }

    with ASGITestClient(app, raise_app_exceptions=True) as real_client:
        write_body = assert_success_response(
            real_client.post("/api/v1/knowledge/ingest", json=knowledge)
        )
        search_body = assert_success_response(
            real_client.post("/api/v1/memory/search", json=search)
        )

    written_id = write_body["data"]["items"][0]["memory"]["memory_id"]
    returned_ids = {
        item["memory"]["memory_id"] for item in search_body["data"]["items"]
    }
    assert written_id in returned_ids


def test_v122_compatibility_endpoints_execute_against_service_and_database(
    monkeypatch,
):
    monkeypatch.setenv("OS_AGENT_ENV", "development")
    now = datetime.now(timezone.utc).isoformat()
    knowledge = {
        "request_id": "req_compat_knowledge",
        "idempotency_key": "idem_compat_knowledge",
        "user_id": "usr_compat",
        "source_event_id": "evt_compat_knowledge",
        "records": [
            {
                "title": "compatibility record",
                "knowledge_type": "fact",
                "body": "compatibility endpoint persists this record",
                "steps": [],
                "keywords": ["compatibility"],
                "source_uri": None,
                "source_reliability": 0.8,
                "effective_at": now,
            }
        ],
    }
    conflict = {
        "request_id": "req_compat_conflict",
        "idempotency_key": "idem_compat_conflict",
        "user_id": "usr_compat",
        "source_event_id": "evt_compat_conflict",
        "decision": {
            "relation": "replace",
            "old_memory_id": "mem_old",
            "new_memory_id": "mem_new",
            "confidence": 0.9,
            "strategy": "keep_new",
            "reason_codes": ["newer_effective_at"],
        },
    }

    with ASGITestClient(app, raise_app_exceptions=True) as real_client:
        written = assert_success_response(
            real_client.post("/api/v1/knowledge", json=knowledge)
        )
        memory_id = written["data"]["items"][0]["memory"]["memory_id"]

        memory = assert_success_response(
            real_client.get(
                f"/api/v1/memory/{memory_id}",
                params={"request_id": "req_compat_get", "user_id": "usr_compat"},
            )
        )
        assert memory["data"]["memory_id"] == memory_id

        versions = assert_success_response(
            real_client.get(
                "/api/v1/preferences/output.format/versions",
                params={
                    "request_id": "req_compat_versions",
                    "user_id": "usr_compat",
                },
            )
        )
        assert versions["data"]["items"] == []

        transitions = assert_success_response(
            real_client.get(
                "/api/v1/memory/transitions",
                params={
                    "request_id": "req_compat_transitions",
                    "user_id": "usr_compat",
                },
            )
        )
        assert transitions["data"] == []

        resolved = assert_success_response(
            real_client.post(
                "/api/v1/knowledge/conflicts/resolve",
                params={"conflict_id": "cfl_compat"},
                json=conflict,
            )
        )
        assert resolved["data"]["conflict_id"] == "cfl_compat"
