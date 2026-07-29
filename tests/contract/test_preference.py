import pytest
from pydantic import ValidationError

from contracts.schemas.preference import PreferenceRecord


def valid_preference_data():
    return {
        "preference_key": "output.format",
        "value": "table",
        "category": "output_style",
        "scope": "scene",
        "scope_value": "office_automation",
        "polarity": "positive",
        "confidence": 0.91,
        "evidence_count": 8,
        "evidence": [{"source_event_id": "evt_123", "weight": 0.8}],
        "revision": 2,
        "status": "active",
    }


def test_preference_record_accepts_valid_input():
    record = PreferenceRecord.model_validate(valid_preference_data())

    assert record.preference_key == "output.format"
    assert record.value == "table"
    assert record.revision == 2


@pytest.mark.parametrize("confidence", [0.0, 1.0])
def test_preference_record_accepts_confidence_boundaries(confidence):
    data = valid_preference_data()
    data["confidence"] = confidence
    data["revision"] = 1

    record = PreferenceRecord.model_validate(data)

    assert record.confidence == confidence
    assert record.revision == 1


@pytest.mark.parametrize(
    "field",
    ["preference_key", "category", "scope_value"],
)
def test_preference_record_rejects_empty_required_strings(field):
    data = valid_preference_data()
    data[field] = " "

    with pytest.raises(ValidationError):
        PreferenceRecord.model_validate(data)


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_preference_record_rejects_confidence_outside_unit_interval(confidence):
    data = valid_preference_data()
    data["confidence"] = confidence

    with pytest.raises(ValidationError):
        PreferenceRecord.model_validate(data)


@pytest.mark.parametrize("revision", [0, -1])
def test_preference_record_rejects_revision_below_one(revision):
    data = valid_preference_data()
    data["revision"] = revision

    with pytest.raises(ValidationError):
        PreferenceRecord.model_validate(data)


def test_preference_record_rejects_negative_evidence_count():
    data = valid_preference_data()
    data["evidence_count"] = -1

    with pytest.raises(ValidationError):
        PreferenceRecord.model_validate(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("scope", "unknown"),
        ("polarity", "unknown"),
        ("status", "unknown"),
    ],
)
def test_preference_record_rejects_unknown_enum_values(field, value):
    data = valid_preference_data()
    data[field] = value

    with pytest.raises(ValidationError):
        PreferenceRecord.model_validate(data)


def test_preference_record_rejects_non_json_evidence():
    data = valid_preference_data()
    data["evidence"] = [{"bad": object()}]

    with pytest.raises(ValidationError):
        PreferenceRecord.model_validate(data)


def test_preference_record_rejects_empty_id_in_evidence():
    data = valid_preference_data()
    data["evidence"] = [{"source_event_id": " ", "weight": 0.8}]

    with pytest.raises(ValidationError):
        PreferenceRecord.model_validate(data)
