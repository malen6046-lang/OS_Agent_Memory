from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from contracts.schemas.envelope import Envelope


def valid_envelope_data():
    return {
        "contract_version": "1.0",
        "request_id": "req_123",
        "idempotency_key": "idem_123",
        "user_id": "usr_123",
        "session_id": "ses_123",
        "scene": "office_automation",
        "source": "tool_result",
        "source_event_id": "evt_123",
        "occurred_at": datetime(2026, 7, 28, 15, 30, tzinfo=timezone.utc),
        "payload": {"ok": True, "count": 1, "nested": {"value": None}},
    }


def test_envelope_accepts_valid_input():
    envelope = Envelope.model_validate(valid_envelope_data())

    assert envelope.contract_version == "1.0"
    assert envelope.session_id == "ses_123"
    assert envelope.occurred_at.tzinfo is not None
    assert envelope.payload["nested"] == {"value": None}


def test_envelope_allows_null_session_id():
    data = valid_envelope_data()
    data["session_id"] = None

    assert Envelope.model_validate(data).session_id is None


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("request_id", ""),
        ("idempotency_key", "   "),
        ("user_id", ""),
        ("session_id", ""),
        ("source_event_id", ""),
    ],
)
def test_envelope_rejects_empty_identifiers(field, invalid_value):
    data = valid_envelope_data()
    data[field] = invalid_value

    with pytest.raises(ValidationError):
        Envelope.model_validate(data)


def test_envelope_rejects_naive_occurred_at():
    data = valid_envelope_data()
    data["occurred_at"] = datetime(2026, 7, 28, 15, 30)

    with pytest.raises(ValidationError):
        Envelope.model_validate(data)


def test_envelope_rejects_non_json_payload():
    data = valid_envelope_data()
    data["payload"] = {"bad": object()}

    with pytest.raises(ValidationError):
        Envelope.model_validate(data)


def test_envelope_rejects_non_dict_payload():
    data = valid_envelope_data()
    data["payload"] = ["not", "a", "dict"]

    with pytest.raises(ValidationError):
        Envelope.model_validate(data)


def test_envelope_rejects_unknown_source_and_contract_version():
    for field, value in (("source", "unknown"), ("contract_version", "1.1")):
        data = valid_envelope_data()
        data[field] = value

        with pytest.raises(ValidationError):
            Envelope.model_validate(data)
