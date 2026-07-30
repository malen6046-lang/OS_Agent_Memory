from datetime import datetime, timezone
from math import nan

import pytest
from pydantic import ValidationError

from contracts.schemas import (
    Envelope,
    EvaluationRunRequest,
    MemoryCreate,
    MemoryResponse,
    MemoryUpdate,
    PreferenceCreate,
    PreferenceResponse,
    SearchRequest,
)

NOW = datetime.now(timezone.utc)


def memory_create_data() -> dict:
    return {
        "user_id": "usr_test",
        "memory_kind": "semantic",
        "subtype": "fact",
        "content_text": "用户喜欢深色主题",
        "content": {"text": "用户喜欢深色主题"},
        "confidence": 0.5,
        "importance": 0.5,
        "valid_from": NOW.isoformat(),
        "valid_to": None,
        "expires_at": None,
        "scene_tags": ["office_automation"],
        "source_refs": ["evt_test"],
        "supersedes": [],
        "attributes": {},
    }


def test_extra_field_is_rejected():
    with pytest.raises(ValidationError):
        SearchRequest(
            request_id="req_test",
            user_id="usr_test",
            query="test",
            top_k=5,
            illegal_field=True,
        )


def test_missing_required_field_is_rejected():
    with pytest.raises(ValidationError):
        SearchRequest(request_id="req_test", query="test")


@pytest.mark.parametrize("confidence", [0, 0.5, 1])
def test_confidence_boundaries_are_accepted(confidence):
    data = memory_create_data()
    data["confidence"] = confidence
    assert MemoryCreate.model_validate(data).confidence == confidence


@pytest.mark.parametrize("confidence", [-0.0001, 1.0001, "0.5", True, nan])
def test_invalid_confidence_is_rejected(confidence):
    data = memory_create_data()
    data["confidence"] = confidence
    with pytest.raises(ValidationError):
        MemoryCreate.model_validate(data)


@pytest.mark.parametrize("top_k", [1, 5, 100])
def test_top_k_boundaries_are_accepted(top_k):
    model = SearchRequest(
        request_id="req_test",
        user_id="usr_test",
        query="test",
        top_k=top_k,
    )
    assert model.top_k == top_k


@pytest.mark.parametrize("top_k", [0, -1, 101, "5", True])
def test_invalid_top_k_is_rejected(top_k):
    with pytest.raises(ValidationError):
        SearchRequest(
            request_id="req_test",
            user_id="usr_test",
            query="test",
            top_k=top_k,
        )


def test_timezone_aware_datetime_is_required():
    valid = memory_create_data()
    assert MemoryCreate.model_validate(valid).valid_from.tzinfo is not None

    invalid = memory_create_data()
    invalid["valid_from"] = "2026-07-30T10:00:00"
    with pytest.raises(ValidationError):
        MemoryCreate.model_validate(invalid)


def test_contract_version_is_frozen():
    base = {
        "request_id": "req_test",
        "idempotency_key": "idem_test",
        "user_id": "usr_test",
        "session_id": None,
        "scene": "office_automation",
        "source": "manual_config",
        "source_event_id": "evt_test",
        "occurred_at": NOW.isoformat(),
        "payload": {},
    }
    assert Envelope.model_validate(base).contract_version == "1.0.0"
    with pytest.raises(ValidationError):
        Envelope.model_validate({**base, "contract_version": "1.0"})


def test_memory_create_rejects_platform_fields():
    with pytest.raises(ValidationError):
        MemoryCreate.model_validate(
            {
                **memory_create_data(),
                "memory_id": "mem_illegal",
                "status": "active",
                "revision": 1,
            }
        )


def test_memory_update_requires_change_and_expected_revision():
    with pytest.raises(ValidationError):
        MemoryUpdate(expected_revision=1)
    with pytest.raises(ValidationError):
        MemoryUpdate(content_text="new")
    assert MemoryUpdate(content_text="new", expected_revision=1).expected_revision == 1


@pytest.mark.parametrize("field", ["user_id", "memory_kind", "subtype", "status"])
def test_memory_update_rejects_immutable_fields(field):
    with pytest.raises(ValidationError):
        MemoryUpdate.model_validate(
            {"content_text": "new", "expected_revision": 1, field: "invalid"}
        )


def test_memory_response_requires_platform_fields():
    with pytest.raises(ValidationError):
        MemoryResponse.model_validate(memory_create_data())
    response = MemoryResponse.model_validate(
        {
            **memory_create_data(),
            "memory_id": "mem_test",
            "status": "active",
            "revision": 1,
        }
    )
    assert response.memory_id == "mem_test"


def test_preference_scope_rules():
    common = {
        "user_id": "usr_test",
        "preference_key": "output.format",
        "value": "table",
        "category": "output_style",
        "polarity": "positive",
        "confidence": 0.8,
        "evidence": [{"source_event_id": "evt_test", "weight": 0.8}],
    }
    assert PreferenceCreate(**common, scope="global", scope_value=None)
    assert PreferenceCreate(
        **common, scope="scene", scope_value="office_automation"
    )
    with pytest.raises(ValidationError):
        PreferenceCreate(**common, scope="global", scope_value="unexpected")
    with pytest.raises(ValidationError):
        PreferenceCreate(**common, scope="tool", scope_value=None)


def test_preference_response_evidence_count_must_match():
    data = {
        "user_id": "usr_test",
        "preference_key": "output.format",
        "value": "table",
        "category": "output_style",
        "scope": "global",
        "scope_value": None,
        "polarity": "positive",
        "confidence": 0.8,
        "evidence": [{"source_event_id": "evt_test", "weight": 0.8}],
        "evidence_count": 2,
        "revision": 1,
        "status": "active",
    }
    with pytest.raises(ValidationError):
        PreferenceResponse.model_validate(data)


def test_evaluation_enum_rejects_integration():
    with pytest.raises(ValidationError):
        EvaluationRunRequest(
            request_id="req_test",
            user_id="usr_test",
            evaluation_types=["integration"],
            attributes={},
        )
