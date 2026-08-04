import pytest
from contracts.schemas.preference import PreferenceRecord

VALID = {
    "preference_key": "output.format",
    "value": "table",
    "category": "output_style",
    "scope": "global",
    "scope_value": "office",
    "polarity": "positive",
    "confidence": 0.91,
    "evidence_count": 2,
    "evidence": [{"source_event_id": "evt_x", "weight": 0.8}],
    "revision": 1,
    "status": "active",
}

def test_valid():
    p = PreferenceRecord.model_validate(VALID)
    assert p.preference_key == "output.format"

def test_missing_key():
    data = {**VALID}; del data["preference_key"]
    with pytest.raises(Exception): PreferenceRecord.model_validate(data)

def test_bad_confidence():
    data = {**VALID, "confidence": 2.0}
    with pytest.raises(Exception): PreferenceRecord.model_validate(data)

def test_bad_revision():
    data = {**VALID, "revision": 0}
    with pytest.raises(Exception): PreferenceRecord.model_validate(data)

def test_invalid_polarity():
    data = {**VALID, "polarity": "neutral"}
    with pytest.raises(Exception): PreferenceRecord.model_validate(data)

def test_negative_evidence_count():
    data = {**VALID, "evidence_count": -1}
    with pytest.raises(Exception): PreferenceRecord.model_validate(data)
