from datetime import datetime, timezone


def event(request_id: str = "req_test") -> dict:
    return {
        "contract_version": "1.0.0",
        "request_id": request_id,
        "idempotency_key": "idem_test",
        "user_id": "usr_test",
        "session_id": "ses_test",
        "scene": "office_automation",
        "source": "manual_config",
        "source_event_id": "evt_test",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "payload": {"content": "使用表格输出"},
    }


def write_context() -> dict:
    return {
        "request_id": "req_test",
        "idempotency_key": "idem_test",
        "user_id": "usr_test",
        "source_event_id": "evt_test",
    }


def assert_success(response, status_code: int = 200):
    assert response.status_code == status_code, response.text
    body = response.json()
    assert body["success"] is True
    assert body["request_id"]
    assert "data" in body
    assert "meta" in body


def test_events_ingest(client):
    response = client.post("/api/v1/events/ingest", json={"events": [event()]})
    assert_success(response)
    assert response.json()["data"]["items"][0]["source_event_id"] == "evt_test"


def test_preferences_extract(client):
    response = client.post(
        "/api/v1/preferences/extract", json={"events": [event()]}
    )
    assert_success(response)
    assert response.json()["data"] == {"candidates": []}


def test_preferences_get(client):
    assert_success(
        client.get(
            "/api/v1/preferences",
            params={
                "request_id": "req_test",
                "user_id": "usr_test",
                "scene": "office_automation",
            },
        )
    )


def test_preferences_history(client):
    assert_success(
        client.get(
            "/api/v1/preferences/output.format/history",
            params={"request_id": "req_test", "user_id": "usr_test"},
        )
    )


def test_knowledge_ingest(client):
    payload = {
        **write_context(),
        "records": [
            {
                "title": "终端打开方式",
                "knowledge_type": "workflow",
                "body": "打开终端",
                "steps": ["点击终端"],
                "keywords": ["终端"],
                "source_uri": None,
                "source_reliability": 0.8,
                "effective_at": datetime.now(timezone.utc).isoformat(),
            }
        ],
    }
    response = client.post("/api/v1/knowledge/ingest", json=payload)
    assert_success(response)
    assert response.json()["data"]["items"][0]["memory"]["memory_id"].startswith(
        "mem_"
    )


def test_memory_search(client):
    assert_success(
        client.post(
            "/api/v1/memory/search",
            json={
                "request_id": "req_test",
                "user_id": "usr_test",
                "query": "如何打开终端",
                "filters": {
                    "scene": "office_automation",
                    "memory_kinds": ["semantic"],
                    "attributes": {},
                },
                "top_k": 5,
            },
        )
    )


def test_conflict_resolve(client):
    payload = {
        **write_context(),
        "decision": {
            "relation": "replace",
            "old_memory_id": "mem_old",
            "new_memory_id": "mem_new",
            "confidence": 0.9,
            "strategy": "keep_new",
            "reason_codes": ["newer_effective_at"],
        },
    }
    assert_success(client.post("/api/v1/conflicts/cfl_test/resolve", json=payload))


def test_forget_preview(client):
    response = client.post(
        "/api/v1/forget/preview",
        json={
            "request_id": "req_test",
            "user_id": "usr_test",
            "instruction": "忘记终端相关记忆",
            "scene": "office_automation",
        },
    )
    assert_success(response)
    assert response.json()["data"]["risk_level"] == "low"


def test_forget_execute(client):
    payload = {
        **write_context(),
        "confirmation_token": "token_test",
        "selected_ids": ["mem_test"],
    }
    response = client.post("/api/v1/forget/execute", json=payload)
    assert_success(response)
    assert response.json()["data"]["requested_ids"] == ["mem_test"]
    assert response.json()["data"]["tombstoned_ids"] == []


def test_promotions_run(client):
    response = client.post(
        "/api/v1/memory/promotions/run",
        json={**write_context(), "scene": "office_automation"},
    )
    assert_success(response)
    assert response.json()["data"]["promoted_count"] == 0
    assert response.json()["data"]["promoted_ids"] == []


def test_health(client):
    response = client.get("/api/v1/health")
    assert_success(response)
    data = response.json()["data"]
    assert data["contract_version"] == "1.0.0"
    assert set(data) == {
        "status",
        "service_version",
        "contract_version",
        "components",
        "model_info",
        "index_info",
    }


def test_evaluations_run(client):
    response = client.post(
        "/api/v1/evaluations/run",
        json={
            "request_id": "req_test",
            "user_id": "usr_test",
            "evaluation_types": ["retrieval", "performance"],
            "attributes": {},
        },
    )
    assert_success(response, status_code=202)
    assert response.json()["data"]["status"] == "accepted"


def test_validation_error_uses_unified_shape(client):
    response = client.post("/api/v1/memory/search", json={})
    assert response.status_code == 422
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert isinstance(body["error"]["details"]["errors"][0]["loc"], list)


def test_request_id_header_and_body_must_match(client):
    response = client.post(
        "/api/v1/memory/search",
        headers={"X-Request-ID": "req_header"},
        json={
            "request_id": "req_body",
            "user_id": "usr_test",
            "query": "测试",
            "top_k": 5,
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert body["request_id"] == "req_body"
    assert body["error"]["code"] == "VALIDATION_ERROR"
