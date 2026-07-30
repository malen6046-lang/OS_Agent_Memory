import pytest
from datetime import datetime, timezone
from pydantic import ValidationError
from contracts.schemas.memory import MemoryRecord


def valid_memory_data():
    return {
        "memory_id": "mem_123",
        "user_id": "usr_123",
        "memory_kind": "preference",
        "subtype": "output_style",
        "content_text": "Use a table for comparisons.",
        "content": {"format": "table", "options": ["compact"]},
        "status": "active",
        "confidence": 0.91,
        "importance": 0.8,
        "revision": 3,
        "valid_from": datetime(2026, 7, 28, 15, 30, tzinfo=timezone.utc),
        "valid_to": None,
        "expires_at": None,
        "scene_tags": ["office_automation"],
        "source_refs": ["evt_123"],
        "supersedes": ["mem_old"],
        "attributes": {"reviewed": True},
    }


def test_memory_record_accepts_valid_input():
    record = MemoryRecord.model_validate(valid_memory_data())
    assert record.memory_id == "mem_123"
    assert record.confidence == pytest.approx(0.91)
    assert record.importance == pytest.approx(0.8)
    assert record.revision == 3
    assert record.valid_from.tzinfo is not None


@pytest.mark.parametrize("value", [0.0, 1.0])
def test_memory_record_accepts_score_boundaries(value):
    data = valid_memory_data()
    data["confidence"] = value
    data["importance"] = value
    data["revision"] = 1
    record = MemoryRecord.model_validate(data)
    assert record.confidence == value
    assert record.importance == value
    assert record.revision == 1


@pytest.mark.parametrize("field", ["memory_id", "user_id"])
def test_memory_record_rejects_empty_ids(field):
    data = valid_memory_data()
    data[field] = " "
    with pytest.raises(ValidationError):
        MemoryRecord.model_validate(data)


@pytest.mark.parametrize("field", ["source_refs", "supersedes"])
def test_memory_record_rejects_empty_ids_in_lists(field):
    data = valid_memory_data()
    data[field] = [""]
    with pytest.raises(ValidationError):
        MemoryRecord.model_validate(data)


@pytest.mark.parametrize("field", ["valid_from", "valid_to", "expires_at"])
def test_memory_record_rejects_naive_datetimes(field):
    data = valid_memory_data()
    data[field] = datetime(2026, 7, 28, 15, 30)
    with pytest.raises(ValidationError):
        MemoryRecord.model_validate(data)


@pytest.mark.parametrize("field", ["confidence", "importance"])
@pytest.mark.parametrize("value", [-0.01, 1.01])
def test_memory_record_rejects_scores_outside_unit_interval(field, value):
    data = valid_memory_data()
    data[field] = value
    with pytest.raises(ValidationError):
        MemoryRecord.model_validate(data)


@pytest.mark.parametrize("revision", [0, -1])
def test_memory_record_rejects_revision_below_one(revision):
    data = valid_memory_data()
    data["revision"] = revision
    with pytest.raises(ValidationError):
        MemoryRecord.model_validate(data)


@pytest.mark.parametrize("field", ["content", "attributes"])
def test_memory_record_rejects_non_dict_json_fields(field):
    data = valid_memory_data()
    data[field] = ["not", "a", "dict"]
    with pytest.raises(ValidationError):
        MemoryRecord.model_validate(data)


@pytest.mark.parametrize("field", ["content", "attributes"])
def test_memory_record_rejects_non_json_values(field):
    data = valid_memory_data()
    data[field] = {"bad": object()}
    with pytest.raises(ValidationError):
        MemoryRecord.model_validate(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("memory_kind", "unknown"),
        ("subtype", "unknown"),
        ("status", "unknown"),
    ],
)
def test_memory_record_rejects_unknown_enum_values(field, value):
    data = valid_memory_data()
    data[field] = value
    with pytest.raises(ValidationError):
        MemoryRecord.model_validate(data)
