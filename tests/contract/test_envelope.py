import pytest
from datetime import datetime, timezone
from contracts.schemas.envelope import Envelope

VALID = {
    "contract_version": "1.0",
    "request_id": "req_abc123",
    "idempotency_key": "idem_xyz",
    "user_id": "usr_001",
    "scene": "office_automation",
    "source": "tool_result",
    "source_event_id": "evt_001",
    "occurred_at": datetime(2026, 7, 28, 15, 30, tzinfo=timezone.utc),
    "payload": {"text": "hello"},
}

def test_valid():
    e = Envelope.model_validate(VALID)
    assert e.request_id == "req_abc123"

def test_missing_user_id():
    data = {**VALID}; del data["user_id"]
    with pytest.raises(Exception): Envelope.model_validate(data)

def test_wrong_source():
    data = {**VALID, "source": "invalid"}
    with pytest.raises(Exception): Envelope.model_validate(data)

def test_no_timezone():
    data = {**VALID, "occurred_at": datetime(2026, 7, 28, 15, 30)}
    with pytest.raises(Exception): Envelope.model_validate(data)

def test_empty_id():
    data = {**VALID, "request_id": ""}
    with pytest.raises(Exception): Envelope.model_validate(data)
