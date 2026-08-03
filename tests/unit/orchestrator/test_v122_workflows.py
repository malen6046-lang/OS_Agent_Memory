import asyncio
import logging
from datetime import datetime, timezone

from app.orchestrator import MemoryOrchestrator


def run(coroutine):
    return asyncio.run(coroutine)


def envelope_payload(**overrides):
    payload = {
        "contract_version": "1.0",
        "request_id": "req_ingest",
        "idempotency_key": "idem_ingest",
        "user_id": "usr_1",
        "session_id": None,
        "scene": "office_automation",
        "source": "tool_result",
        "source_event_id": "evt_1",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "payload": {"content": "safe"},
    }
    payload.update(overrides)
    return payload


class PreferenceStub:
    async def extract(self, events):
        return [{"candidate": events[0].source_event_id}]

    async def upsert(self, candidates):
        return [{"preference": candidates[0]["candidate"]}]


class KnowledgeStub:
    async def ingest(self, records):
        return {"records": [{"memory_id": "mem_1"}]}


class RetrieverStub:
    async def search(self, request):
        return {"items": []}


class ForgetStub:
    async def preview(self, request):
        return {
            "candidates": ["mem_1"],
            "confirmation_token": "confirm_1",
        }

    async def execute(self, request):
        return {
            "memory_ids": ["mem_1"],
            "vector_pks": [101],
            "status": "executed",
        }


def make_orchestrator(**overrides):
    dependencies = {
        "preference_service": PreferenceStub(),
        "knowledge_service": KnowledgeStub(),
        "retriever": RetrieverStub(),
        "forget_service": ForgetStub(),
    }
    dependencies.update(overrides)
    return MemoryOrchestrator(**dependencies)


def test_ingest_runs_frozen_flow_in_order_and_returns_unified_response():
    order = []

    class IdempotencySpy:
        def get(self, user_id, operation, key):
            order.append("idempotency.get")
            assert (user_id, operation, key) == (
                "usr_1",
                "ingest",
                "idem_ingest",
            )
            return None

        def save(self, user_id, operation, key, fingerprint, response):
            order.append("idempotency.save")
            assert fingerprint
            assert response["success"] is True
            return {"saved": True}

    class SafetySpy:
        async def check(self, envelope):
            order.append("safety.check")
            return {"allowed": True}

    class PreferenceSpy:
        async def extract(self, events):
            order.append("preference.extract")
            return ["candidate_1"]

        async def upsert(self, candidates):
            order.append("preference.upsert")
            assert candidates == ["candidate_1"]
            return ["preference_1"]

    class KnowledgeSpy:
        async def ingest(self, records):
            order.append("knowledge.ingest")
            return {"records": ["knowledge_1"]}

    class RepositorySpy:
        def commit(self, result):
            order.append("repository.commit")
            assert result["preferences"] == ["preference_1"]
            return {"records": [{"memory_id": "mem_1", "vector_pk": 101}]}

    class VectorSpy:
        async def upsert(self, items):
            order.append("vector.upsert")
            assert items[0]["vector_pk"] == 101
            return {"upserted": 1}

    class AuditSpy:
        def record(self, event):
            order.append("audit.record")
            assert event["operation"] == "memory.ingest"
            assert "content" not in event["metadata"]
            return {"audit_id": "audit_1"}

    orchestrator = make_orchestrator(
        preference_service=PreferenceSpy(),
        knowledge_service=KnowledgeSpy(),
        safety_service=SafetySpy(),
        idempotency_repository=IdempotencySpy(),
        repository=RepositorySpy(),
        vector_store=VectorSpy(),
        audit_repository=AuditSpy(),
    )

    response = run(orchestrator.ingest(envelope_payload()))

    assert response["success"] is True
    assert response["request_id"] == "req_ingest"
    assert response["meta"]["degraded"] is False
    assert response["data"]["vector_result"] == {"upserted": 1}
    assert order == [
        "idempotency.get",
        "safety.check",
        "preference.extract",
        "preference.upsert",
        "knowledge.ingest",
        "repository.commit",
        "vector.upsert",
        "audit.record",
        "idempotency.save",
    ]


def test_ingest_replay_stops_before_safety_and_service_calls():
    stored_response = {
        "success": True,
        "request_id": "req_ingest",
        "data": {"memory_ids": ["mem_existing"]},
        "error": None,
        "meta": {"elapsed_ms": 1, "degraded": False},
    }

    class IdempotencyReplay:
        async def get(self, user_id, operation, key):
            return {"response": stored_response}

    class MustNotRun:
        async def check(self, request):
            raise AssertionError("safety must not run on replay")

    orchestrator = make_orchestrator(
        idempotency_repository=IdempotencyReplay(),
        safety_service=MustNotRun(),
    )

    response = run(
        orchestrator.ingest(envelope_payload(request_id="req_retry"))
    )

    assert response["data"] == {"memory_ids": ["mem_existing"]}
    assert response["request_id"] == "req_retry"
    assert response["meta"]["idempotent_replay"] is True
    assert stored_response["request_id"] == "req_ingest"
    assert "idempotent_replay" not in stored_response["meta"]


def test_ingest_rejects_blocked_content_before_writes():
    class EmptyIdempotency:
        async def get(self, *args):
            return None

    class BlockingSafety:
        async def check(self, request):
            return {"allowed": False, "entity_types": ["phone"]}

    orchestrator = make_orchestrator(
        idempotency_repository=EmptyIdempotency(),
        safety_service=BlockingSafety(),
    )

    response = run(orchestrator.ingest(envelope_payload()))

    assert response["success"] is False
    assert response["error"]["code"] == "SENSITIVE_CONTENT_BLOCKED"
    assert "safe" not in str(response)


def test_ingest_rejects_invalid_envelope_before_dependencies():
    response = run(make_orchestrator().ingest({"request_id": "req_bad"}))

    assert response["success"] is False
    assert response["request_id"] == "req_bad"
    assert response["error"]["code"] == "VALIDATION_ERROR"


def test_search_enforces_user_and_active_status_filters():
    class MixedRetriever:
        async def search(self, request):
            return {
                "items": [
                    {"memory_id": "keep", "user_id": "usr_1", "status": "active"},
                    {"memory_id": "other", "user_id": "usr_2", "status": "active"},
                    {"memory_id": "deleted", "user_id": "usr_1", "status": "tombstoned"},
                    {"memory_id": "unknown", "user_id": "usr_1"},
                ],
                "total": 4,
            }

    orchestrator = make_orchestrator(retriever=MixedRetriever())

    response = run(
        orchestrator.search(
            {"request_id": "req_search", "user_id": "usr_1", "query": "format"}
        )
    )

    assert response["success"] is True
    assert [item["memory_id"] for item in response["data"]["items"]] == ["keep"]
    assert response["data"]["total"] == 1
    assert response["meta"] == {
        "elapsed_ms": response["meta"]["elapsed_ms"],
        "degraded": False,
        "provider": "hybrid",
    }


def test_search_marks_fallback_result_as_degraded():
    class UnavailableRetriever:
        async def search(self, request):
            raise ConnectionError("vendor details must not escape")

    class FallbackRetriever:
        def search(self, request):
            return {
                "items": [
                    {"memory_id": "mem_1", "user_id": "usr_1", "status": "active"}
                ]
            }

    orchestrator = make_orchestrator(
        retriever=UnavailableRetriever(),
        fallback_retriever=FallbackRetriever(),
    )

    response = run(
        orchestrator.search(
            {"request_id": "req_search", "user_id": "usr_1", "query": "format"}
        )
    )

    assert response["success"] is True
    assert response["meta"]["degraded"] is True
    assert response["meta"]["provider"] == "fallback"
    assert response["meta"]["degradation_reason"] == "DEPENDENCY_UNAVAILABLE"


def test_search_timeout_is_converted_to_frozen_error_code():
    class SlowRetriever:
        async def search(self, request):
            await asyncio.sleep(0.05)
            return {"items": []}

    orchestrator = make_orchestrator(
        retriever=SlowRetriever(), timeout_seconds=0.005
    )

    response = run(
        orchestrator.search(
            {"request_id": "req_slow", "user_id": "usr_1", "query": "format"}
        )
    )

    assert response["success"] is False
    assert response["error"]["code"] == "SEARCH_TIMEOUT"
    assert response["error"]["retryable"] is True


def test_preview_forget_only_returns_candidates_and_token():
    class PreviewSpy:
        async def preview(self, request):
            return {
                "candidate_list": ["mem_1"],
                "confirmation_token": "confirm_1",
            }

        async def execute(self, request):
            raise AssertionError("preview cannot execute deletion")

    response = run(
        make_orchestrator(forget_service=PreviewSpy()).preview_forget(
            {
                "request_id": "req_preview",
                "user_id": "usr_1",
                "instruction": "forget mem_1",
            }
        )
    )

    assert response["success"] is True
    assert response["data"]["candidate_list"] == ["mem_1"]
    assert response["data"]["confirmation_token"] == "confirm_1"


def test_execute_forget_orders_logical_vector_and_audit_steps():
    order = []

    class ForgetSpy:
        async def execute(self, request):
            order.append("logical_delete")
            return {"memory_ids": ["mem_1"], "vector_pks": [101]}

    class VectorSpy:
        async def delete(self, vector_pks):
            order.append("vector_delete")
            assert vector_pks == [101]
            return {"deleted": 1}

    class AuditSpy:
        async def record(self, event):
            order.append("audit")
            assert event["metadata"]["memory_ids"] == ["mem_1"]
            return {"audit_id": "audit_1"}

    response = run(
        make_orchestrator(
            forget_service=ForgetSpy(),
            vector_store=VectorSpy(),
            audit_repository=AuditSpy(),
        ).execute_forget(
            {
                "request_id": "req_forget",
                "user_id": "usr_1",
                "confirmation_token": "confirm_1",
                "selected_ids": ["mem_1"],
            }
        )
    )

    assert response["success"] is True
    assert order == ["logical_delete", "vector_delete", "audit"]


def test_run_evaluation_delegates_and_wraps_result():
    class EvaluationSpy:
        async def run(self, request):
            return {"run_id": "run_1", "status": "completed"}

    response = run(
        make_orchestrator(evaluation_service=EvaluationSpy()).run_evaluation(
            {"request_id": "req_eval", "metric_names": ["recall"]}
        )
    )

    assert response["success"] is True
    assert response["data"]["run_id"] == "run_1"


def test_flow_logs_include_flow_step_and_request_id(caplog):
    caplog.set_level(logging.INFO)

    run(
        make_orchestrator().search(
            {"request_id": "req_log", "user_id": "usr_1", "query": "format"}
        )
    )

    records = [record for record in caplog.records if record.message == "memory_orchestrator"]
    assert [(record.flow, record.step) for record in records] == [
        ("search", "start"),
        ("search", "filtered"),
    ]
    assert all(record.request_id == "req_log" for record in records)
