import asyncio
import logging
from datetime import datetime, timezone

from app.orchestrator import MemoryOrchestrator
from app.orchestrator.memory_orchestrator import _envelope_fingerprint
from contracts.schemas.envelope import Envelope
from contracts.schemas.evaluation import EvaluationRun
from contracts.schemas.forget import ForgetExecutionPlan, ForgetPlan
from contracts.schemas.knowledge import IngestResult
from contracts.schemas.persistence import (
    AuditResult,
    IdempotencyEntry,
    IngestCommitResult,
    LogicalDeleteResult,
)
from contracts.schemas.preference import PreferenceCandidate, PreferenceRecord
from contracts.schemas.provider import DeleteResult, UpsertResult, VectorItem
from contracts.schemas.retrieval import SearchHit, SearchResponse
from contracts.schemas.safety import SafetyCheckResult


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
    def extract(self, events):
        return []

    def upsert(self, candidates):
        return []


class KnowledgeStub:
    def ingest(self, events, preferences):
        return IngestResult()


class RetrieverStub:
    def search(self, request):
        return SearchResponse(
            request_id=request.request_id,
            user_id=request.user_id,
            items=[],
            total=0,
            provider="mock",
        )


class ForgetStub:
    def preview(self, request):
        return ForgetPlan(
            plan_id="plan_1",
            user_id=request.user_id,
            candidates=[{"memory_id": "mem_1", "user_id": request.user_id}],
            risk_level="low",
            confirmation_token="confirm_1",
            expires_at=datetime.now(timezone.utc).replace(year=2030),
        )

    def execute(self, request):
        return ForgetExecutionPlan(
            request_id=request.request_id,
            user_id=request.user_id,
            plan_id=request.plan_id,
            memory_ids=request.selected_ids,
            expires_at=datetime.now(timezone.utc).replace(year=2030),
        )


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

        def save(self, entry):
            order.append("idempotency.save")
            assert entry.fingerprint
            assert entry.response["success"] is True

    class SafetySpy:
        def check(self, envelope):
            order.append("safety.check")
            return SafetyCheckResult(allowed=True)

    class PreferenceSpy:
        def extract(self, events):
            order.append("preference.extract")
            return [
                PreferenceCandidate(
                    user_id="usr_1",
                    preference_key="output.format",
                    value="table",
                    category="output_style",
                    scope="global",
                    scope_value="global",
                    polarity="positive",
                    confidence=0.9,
                )
            ]

        def upsert(self, candidates):
            order.append("preference.upsert")
            return [
                PreferenceRecord(
                    preference_key="output.format",
                    value="table",
                    category="output_style",
                    scope="global",
                    scope_value="global",
                    polarity="positive",
                    confidence=0.9,
                    evidence_count=0,
                    evidence=[],
                    revision=1,
                    status="active",
                )
            ]

    class KnowledgeSpy:
        def ingest(self, events, preferences):
            order.append("knowledge.ingest")
            assert preferences[0].preference_key == "output.format"
            return IngestResult()

    class RepositorySpy:
        def commit_ingest(self, result):
            order.append("repository.commit")
            assert result.preferences[0].preference_key == "output.format"
            return IngestCommitResult(
                vector_items=[
                    VectorItem(
                        vector_pk=101,
                        memory_id="mem_1",
                        user_id="usr_1",
                        status="active",
                        vector=[0.0],
                    )
                ]
            )

    class VectorSpy:
        def upsert(self, items):
            order.append("vector.upsert")
            assert items[0].vector_pk == 101
            return UpsertResult(upserted=1)

    class AuditSpy:
        def record(self, event):
            order.append("audit.record")
            assert event.operation == "memory.ingest"
            assert "content" not in event.metadata
            return AuditResult(audit_id="audit_1")

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
    replay_payload = envelope_payload(
        request_id="req_retry",
        occurred_at="2026-08-03T12:00:00+08:00",
    )
    replay_fingerprint = _envelope_fingerprint(
        Envelope.model_validate(replay_payload)
    )
    stored_response = {
        "success": True,
        "request_id": "req_ingest",
        "data": {"memory_ids": ["mem_existing"]},
        "error": None,
        "meta": {"elapsed_ms": 1, "degraded": False},
    }

    class IdempotencyReplay:
        def get(self, user_id, operation, key):
            return IdempotencyEntry(
                user_id=user_id,
                operation=operation,
                idempotency_key=key,
                fingerprint=replay_fingerprint,
                response=stored_response,
            )

    class MustNotRun:
        def check(self, request):
            raise AssertionError("safety must not run on replay")

    orchestrator = make_orchestrator(
        idempotency_repository=IdempotencyReplay(),
        safety_service=MustNotRun(),
    )

    response = run(orchestrator.ingest(replay_payload))

    assert response["data"] == {"memory_ids": ["mem_existing"]}
    assert response["request_id"] == "req_retry"
    assert response["meta"]["idempotent_replay"] is True
    assert stored_response["request_id"] == "req_ingest"
    assert "idempotent_replay" not in stored_response["meta"]


def test_ingest_rejects_blocked_content_before_writes():
    class EmptyIdempotency:
        def get(self, *args):
            return None

    class BlockingSafety:
        def check(self, request):
            return SafetyCheckResult(
                allowed=False, entity_types=["phone"]
            )

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
        def search(self, request):
            return SearchResponse(
                request_id=request.request_id,
                user_id=request.user_id,
                items=[
                    SearchHit(memory_id="keep", user_id="usr_1", status="active", content_text="keep", score=1.0),
                    SearchHit(memory_id="other", user_id="usr_2", status="active", content_text="other", score=0.9),
                    SearchHit(memory_id="deleted", user_id="usr_1", status="tombstoned", content_text="deleted", score=0.8),
                ],
                total=3,
                provider="hybrid",
            )

    orchestrator = make_orchestrator(retriever=MixedRetriever())

    response = run(
        orchestrator.search(
            {"request_id": "req_search", "user_id": "usr_1", "query": "format"}
        )
    )

    assert response["success"] is True
    assert [item["memory_id"] for item in response["data"]["items"]] == ["keep"]
    assert response["data"]["total"] == 1
    assert response["meta"]["degraded"] is False
    assert response["meta"]["provider"] == "hybrid"


def test_search_marks_fallback_result_as_degraded():
    class UnavailableRetriever:
        def search(self, request):
            raise ConnectionError("vendor details must not escape")

    class FallbackRetriever:
        def search(self, request):
            return SearchResponse(
                request_id=request.request_id,
                user_id=request.user_id,
                items=[
                    SearchHit(
                        memory_id="mem_1",
                        user_id="usr_1",
                        status="active",
                        content_text="fallback",
                        score=1.0,
                    )
                ],
                total=1,
                provider="fallback",
                degraded=True,
            )

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
        def preview(self, request):
            return ForgetPlan(
                plan_id="plan_1",
                user_id=request.user_id,
                candidates=[
                    {"memory_id": "mem_1", "user_id": request.user_id}
                ],
                risk_level="low",
                confirmation_token="confirm_1",
                expires_at=datetime.now(timezone.utc).replace(year=2030),
            )

        def execute(self, request):
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
    assert response["data"]["candidates"][0]["memory_id"] == "mem_1"
    assert response["data"]["confirmation_token"] == "confirm_1"


def test_execute_forget_orders_logical_vector_and_audit_steps():
    order = []

    class ForgetSpy:
        def execute(self, request):
            order.append("validate_execute")
            return ForgetExecutionPlan(
                request_id=request.request_id,
                user_id=request.user_id,
                plan_id=request.plan_id,
                memory_ids=request.selected_ids,
                expires_at=datetime.now(timezone.utc).replace(year=2030),
            )

    class RepositorySpy:
        def logical_delete(self, plan):
            order.append("logical_delete")
            return LogicalDeleteResult(
                plan_id=plan.plan_id,
                user_id=plan.user_id,
                memory_ids=plan.memory_ids,
                vector_pks=[101],
            )

    class VectorSpy:
        def delete(self, vector_pks):
            order.append("vector_delete")
            assert vector_pks == [101]
            return DeleteResult(deleted=1)

    class AuditSpy:
        def record(self, event):
            order.append("audit")
            assert event.metadata["memory_ids"] == ["mem_1"]
            return AuditResult(audit_id="audit_1")

    response = run(
        make_orchestrator(
            forget_service=ForgetSpy(),
            repository=RepositorySpy(),
            vector_store=VectorSpy(),
            audit_repository=AuditSpy(),
        ).execute_forget(
            {
                "request_id": "req_forget",
                "user_id": "usr_1",
                "plan_id": "plan_1",
                "confirmation_token": "confirm_1",
                "selected_ids": ["mem_1"],
            }
        )
    )

    assert response["success"] is True
    assert order == [
        "validate_execute",
        "logical_delete",
        "vector_delete",
        "audit",
    ]


def test_run_evaluation_delegates_and_wraps_result():
    class EvaluationSpy:
        def run(self, request):
            return EvaluationRun(
                run_id="run_1",
                request_id=request.request_id,
                status="completed",
                metrics={"recall": 1.0},
                created_at=datetime.now(timezone.utc),
            )

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
