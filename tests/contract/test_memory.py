import pytest
from datetime import datetime, timezone
from contracts.schemas.memory import MemoryRecord

VALID = {
    "memory_id": "mem_001",
    "user_id": "usr_001",
    "memory_kind": "preference",
    "subtype": "output_style",
    "content_text": "用户偏好深色主题",
    "content": {},
    "status": "active",
    "confidence": 0.9,
    "importance": 0.8,
    "revision": 1,
    "valid_from": datetime(2026, 7, 28, 15, 30, tzinfo=timezone.utc),
    "scene_tags": ["office"],
    "source_refs": ["evt_001"],
    "supersedes": [],
    "attributes": {},
}

def test_valid():
    m = MemoryRecord.model_validate(VALID)
    assert m.memory_id == "mem_001"

def test_missing_user_id():
    data = {**VALID}; del data["user_id"]
    with pytest.raises(Exception): MemoryRecord.model_validate(data)

def test_bad_confidence():
    data = {**VALID, "confidence": 1.5}
    with pytest.raises(Exception): MemoryRecord.model_validate(data)

def test_bad_revision():
    data = {**VALID, "revision": 0}
    with pytest.raises(Exception): MemoryRecord.model_validate(data)

def test_empty_content_text():
    data = {**VALID, "content_text": ""}
    with pytest.raises(Exception): MemoryRecord.model_validate(data)

def test_wrong_kind():
    data = {**VALID, "memory_kind": "unknown"}
    with pytest.raises(Exception): MemoryRecord.model_validate(data)

def test_negative_importance():
    data = {**VALID, "importance": -0.1}
    with pytest.raises(Exception): MemoryRecord.model_validate(data)
