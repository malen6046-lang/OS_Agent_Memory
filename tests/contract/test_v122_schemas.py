from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from contracts.schemas.evaluation import EvaluationRun, EvaluationRunRequest
from contracts.schemas.forget import (
    ForgetExecuteRequest,
    ForgetExecutionPlan,
    ForgetPlan,
    ForgetPreviewRequest,
)
from contracts.schemas.knowledge import ConflictDecision, KnowledgeDraft
from contracts.schemas.persistence import AuditEvent, IdempotencyEntry
from contracts.schemas.provider import EmbeddingBatch, VectorItem
from contracts.schemas.responses import ApiResponse, ErrorDetail, ResponseMeta
from contracts.schemas.retrieval import SearchRequest, SearchResponse


NOW = datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc)


def test_knowledge_and_conflict_schemas_accept_valid_input():
    draft = KnowledgeDraft(
        user_id="usr_1",
        source_event_id="evt_1",
        title="Open terminal",
        knowledge_type="workflow",
        body="Use the terminal shortcut",
        source_reliability=0.8,
        effective_at=NOW,
    )
    decision = ConflictDecision(
        relation="replace",
        old_memory_id="mem_old",
        new_memory_id="mem_new",
        confidence=0.9,
        strategy="keep_new",
    )

    assert draft.effective_at.tzinfo is not None
    assert decision.relation == "replace"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_reliability", 1.1),
        ("effective_at", datetime(2026, 8, 3, 12, 0)),
    ],
)
def test_knowledge_draft_rejects_invalid_input(field, value):
    data = {
        "user_id": "usr_1",
        "source_event_id": "evt_1",
        "title": "Open terminal",
        "knowledge_type": "workflow",
        "body": "Use the terminal shortcut",
        "source_reliability": 0.8,
        "effective_at": NOW,
    }
    data[field] = value

    with pytest.raises(ValidationError):
        KnowledgeDraft.model_validate(data)


def test_search_contracts_validate_limits_and_response_shape():
    request = SearchRequest(
        request_id="req_1",
        user_id="usr_1",
        query="terminal",
        top_k=5,
    )
    response = SearchResponse(
        request_id=request.request_id,
        user_id=request.user_id,
        items=[],
        total=0,
        provider="fallback",
        degraded=True,
    )

    assert response.degraded is True
    with pytest.raises(ValidationError):
        SearchRequest(
            request_id="req_1",
            user_id="usr_1",
            query="terminal",
            top_k=0,
        )


def test_forget_contracts_enforce_two_stage_confirmation():
    preview = ForgetPreviewRequest(
        request_id="req_preview",
        user_id="usr_1",
        memory_ids=["mem_1"],
    )
    plan = ForgetPlan(
        plan_id="plan_1",
        user_id="usr_1",
        candidates=[{"memory_id": "mem_1", "user_id": "usr_1"}],
        risk_level="low",
        confirmation_token="confirm_1",
        expires_at=NOW + timedelta(minutes=5),
    )
    execute = ForgetExecuteRequest(
        request_id="req_execute",
        user_id="usr_1",
        plan_id=plan.plan_id,
        confirmation_token=plan.confirmation_token,
        selected_ids=["mem_1"],
    )

    assert preview.memory_ids == ["mem_1"]
    assert execute.selected_ids == ["mem_1"]
    with pytest.raises(ValidationError):
        ForgetPreviewRequest(request_id="req", user_id="usr_1")
    with pytest.raises(ValidationError):
        ForgetExecutionPlan(
            request_id="req",
            user_id="usr_1",
            plan_id="plan_1",
            memory_ids=["mem_1"],
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )


def test_evaluation_contracts_require_metrics_and_aware_time():
    request = EvaluationRunRequest(
        request_id="req_eval", metric_names=["recall"]
    )
    run = EvaluationRun(
        run_id="run_1",
        request_id=request.request_id,
        status="accepted",
        created_at=NOW,
    )

    assert run.status == "accepted"
    with pytest.raises(ValidationError):
        EvaluationRunRequest(request_id="req_eval", metric_names=[])
    with pytest.raises(ValidationError):
        EvaluationRun(
            run_id="run_1",
            request_id="req_eval",
            status="accepted",
            created_at=datetime(2026, 8, 3, 12, 0),
        )


def test_provider_contracts_reject_dimension_and_primary_key_errors():
    batch = EmbeddingBatch(
        vectors=[[0.1, 0.2]], model_name="mock", dimension=2
    )
    item = VectorItem(
        vector_pk=2**63 - 1,
        memory_id="mem_1",
        user_id="usr_1",
        status="active",
        vector=[0.1, 0.2],
    )

    assert batch.dimension == 2
    assert item.vector_pk == 2**63 - 1
    with pytest.raises(ValidationError):
        EmbeddingBatch(
            vectors=[[0.1]], model_name="mock", dimension=2
        )
    with pytest.raises(ValidationError):
        VectorItem(
            vector_pk=2**63,
            memory_id="mem_1",
            user_id="usr_1",
            status="active",
            vector=[0.1],
        )


def test_response_contract_enforces_success_error_pair_and_meta():
    response = ApiResponse[dict](
        success=True,
        request_id="req_1",
        data={"ok": True},
        meta=ResponseMeta(elapsed_ms=2, degraded=False),
    )

    assert response.error is None
    with pytest.raises(ValidationError):
        ApiResponse[dict](success=False, request_id="req_1")
    with pytest.raises(ValidationError):
        ApiResponse[dict](
            success=True,
            request_id="req_1",
            data={},
            error=ErrorDetail(code="INTERNAL_ERROR", message="failed"),
        )


def test_persistence_metadata_is_json_serializable_and_ids_are_non_empty():
    audit = AuditEvent(
        operation="memory.ingest",
        request_id="req_1",
        user_id="usr_1",
        metadata={"memory_ids": ["mem_1"]},
    )
    entry = IdempotencyEntry(
        user_id="usr_1",
        operation="ingest",
        idempotency_key="idem_1",
        fingerprint="fingerprint_1",
        response={"success": True},
    )

    assert audit.metadata["memory_ids"] == ["mem_1"]
    assert entry.idempotency_key == "idem_1"
    with pytest.raises(ValidationError):
        AuditEvent(
            operation="memory.ingest",
            request_id="",
            user_id="usr_1",
        )

