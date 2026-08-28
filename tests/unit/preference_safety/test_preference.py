"""Acceptance tests for the contract-native preference service."""

from __future__ import annotations

import inspect
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from contracts.schemas.common import PreferenceScope
from contracts.schemas.envelope import Envelope
from contracts.schemas.preference import PreferenceCandidate, PreferenceRecord
from modules.preference_safety import PreferenceService


NOW = datetime(2099, 8, 5, 12, 0, tzinfo=timezone.utc)


def _envelope(
    *,
    user_id: str = "usr_1",
    event_id: str = "evt_1",
    scene: str = "desktop",
    payload: dict | None = None,
) -> Envelope:
    return Envelope(
        contract_version="1.0",
        request_id=f"req_{event_id}",
        idempotency_key=f"idem_{event_id}",
        user_id=user_id,
        scene=scene,
        source="tool_result",
        source_event_id=event_id,
        occurred_at=NOW,
        payload=payload or {"text": "我喜欢深色主题"},
    )


def _candidate(
    *,
    user_id: str = "usr_1",
    value: str = "dark",
    event_id: str = "evt_1",
    scope: PreferenceScope = PreferenceScope.GLOBAL,
    scope_value: str = "global",
    confidence: float = 0.9,
) -> PreferenceCandidate:
    return PreferenceCandidate(
        user_id=user_id,
        preference_key="theme",
        value=value,
        category="ui",
        scope=scope,
        scope_value=scope_value,
        polarity="positive",
        confidence=confidence,
        evidence=[{"source_event_id": event_id, "weight": confidence}],
    )


def test_public_methods_keep_frozen_synchronous_signatures():
    expected = {
        "extract": ["self", "events"],
        "upsert": ["self", "candidates"],
        "resolve": ["self", "user_id", "scene", "keys"],
        "history": ["self", "user_id", "preference_key"],
    }

    for method_name, parameter_names in expected.items():
        method = getattr(PreferenceService, method_name)
        assert not inspect.iscoroutinefunction(method)
        assert list(inspect.signature(method).parameters) == parameter_names


def test_extract_and_upsert_return_frozen_contract_models():
    service = PreferenceService()

    candidates = service.extract([_envelope()])
    records = service.upsert(candidates)

    assert candidates
    assert all(isinstance(item, PreferenceCandidate) for item in candidates)
    assert all(isinstance(item, PreferenceRecord) for item in records)
    candidate = next(
        item for item in candidates if item.preference_key == "theme"
    )
    assert candidate.scope is PreferenceScope.GLOBAL
    assert candidate.scope_value == "global"
    assert candidate.evidence == [
        {"source_event_id": "evt_1", "weight": 0.9}
    ]
    assert set(type(records[0]).model_fields) == {
        "preference_key",
        "value",
        "category",
        "scope",
        "scope_value",
        "polarity",
        "confidence",
        "evidence_count",
        "evidence",
        "revision",
        "status",
    }


def test_rules_match_nested_payload_casefold_and_cjk_normalization_once():
    service = PreferenceService()
    event = _envelope(
        payload={
            "messages": [
                {"text": "我 喜 欢 深 色 主 题，也接受暗 色，并使用 VIM。"}
            ]
        }
    )

    candidates = service.extract([event])

    theme = [item for item in candidates if item.preference_key == "theme"]
    assert len(theme) == 1
    assert theme[0].value == "dark"
    assert any(
        item.preference_key == "editor" and item.value == "vim"
        for item in candidates
    )


def test_short_ascii_rules_do_not_match_inside_larger_words():
    candidates = PreferenceService().extract(
        [_envelope(payload={"text": "Google stores digital documents"})]
    )

    assert not any(
        item.preference_key in {"language", "vcs"}
        for item in candidates
    )


def test_specific_rule_suppresses_its_generic_substring_rule():
    candidates = PreferenceService().extract(
        [_envelope(payload={"text": "请减少动画"})]
    )

    animation_values = [
        item.value
        for item in candidates
        if item.preference_key == "animation"
    ]
    assert animation_values == ["reduced"]


def test_conflicting_values_follow_the_last_explicit_mention():
    service = PreferenceService()

    light_then_dark = service.extract(
        [_envelope(payload={"text": "先浅色，后来深色"})]
    )
    dark_then_light = service.extract(
        [_envelope(payload={"text": "先深色，后来浅色"})]
    )

    assert [
        item.value
        for item in light_then_dark
        if item.preference_key == "theme"
    ] == [
        "dark"
    ]
    assert [
        item.value
        for item in dark_then_light
        if item.preference_key == "theme"
    ] == [
        "light"
    ]


def test_negated_rule_is_extracted_with_negative_polarity():
    candidates = PreferenceService().extract(
        [_envelope(payload={"text": "不要自动更新"})]
    )

    auto_update = next(
        item for item in candidates if item.preference_key == "auto_update"
    )
    assert auto_update.polarity.value == "negative"


def test_resolve_enforces_user_and_scope_isolation_with_scene_precedence():
    service = PreferenceService()
    service.upsert(
        [
            _candidate(user_id="usr_a", value="dark"),
            _candidate(
                user_id="usr_a",
                value="light",
                event_id="evt_scene",
                scope=PreferenceScope.SCENE,
                scope_value="office",
            ),
            _candidate(user_id="usr_b", value="blue", event_id="evt_b"),
        ]
    )

    office = service.resolve("usr_a", "office")
    meeting = service.resolve("usr_a", "meeting")
    other_user = service.resolve("usr_b", "office", keys=["theme"])

    assert [(item.preference_key, item.value) for item in office] == [
        ("theme", "light")
    ]
    assert [(item.preference_key, item.value) for item in meeting] == [
        ("theme", "dark")
    ]
    assert [(item.preference_key, item.value) for item in other_user] == [
        ("theme", "blue")
    ]
    assert service.resolve("usr_a", "office", keys=["editor"]) == []


def test_same_evidence_replay_is_idempotent():
    service = PreferenceService()
    candidate = _candidate()

    first = service.upsert([candidate])[0]
    replay = service.upsert([candidate])[0]

    assert first.revision == replay.revision == 1
    assert replay.evidence_count == 1
    assert len(service.history("usr_1", "theme")) == 1


def test_invalid_candidate_batch_does_not_partially_commit():
    service = PreferenceService()
    invalid = _candidate().model_dump(mode="python")
    invalid["confidence"] = 2.0

    with pytest.raises(ValidationError):
        service.upsert([_candidate(), invalid])

    assert service.resolve("usr_1", "desktop") == []
    assert service.history("usr_1", "theme") == []


def test_new_evidence_creates_an_immutable_revision():
    service = PreferenceService()

    service.upsert([_candidate(event_id="evt_1", confidence=0.8)])
    current = service.upsert(
        [_candidate(event_id="evt_2", confidence=0.9)]
    )[0]
    history = service.history("usr_1", "theme")

    assert current.revision == 2
    assert current.evidence_count == 2
    assert [item.revision for item in history] == [1, 2]
    assert history[0].evidence == [
        {"source_event_id": "evt_1", "weight": 0.8}
    ]
    assert {
        item["source_event_id"] for item in history[1].evidence
    } == {"evt_1", "evt_2"}


def test_history_and_upsert_results_are_deep_copies():
    service = PreferenceService()
    returned = service.upsert([_candidate()])[0]
    returned.value = "tampered"
    returned.evidence[0]["weight"] = 0.0

    first_history = service.history("usr_1", "theme")
    first_history[0].value = "also-tampered"
    first_history[0].evidence[0]["weight"] = 0.1

    fresh_history = service.history("usr_1", "theme")
    fresh_resolve = service.resolve("usr_1", "desktop")
    assert fresh_history[0].value == "dark"
    assert fresh_history[0].evidence[0]["weight"] == 0.9
    assert fresh_resolve[0].value == "dark"
    assert fresh_resolve[0].evidence[0]["weight"] == 0.9


def test_concurrent_unique_evidence_updates_are_atomic():
    service = PreferenceService()
    candidates = [
        _candidate(event_id=f"evt_{index}") for index in range(24)
    ]

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda item: service.upsert([item]), candidates))

    current = service.resolve("usr_1", "desktop")[0]
    history = service.history("usr_1", "theme")
    assert current.revision == 24
    assert current.evidence_count == 24
    assert len(history) == 24
    assert [item.revision for item in history] == list(range(1, 25))
    assert {
        item["source_event_id"] for item in current.evidence
    } == {f"evt_{index}" for index in range(24)}


def test_concurrent_identical_evidence_replays_remain_idempotent():
    service = PreferenceService()
    candidate = _candidate()

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _: service.upsert([candidate]), range(32)))

    current = service.resolve("usr_1", "desktop")[0]
    assert current.revision == 1
    assert current.evidence_count == 1
    assert len(service.history("usr_1", "theme")) == 1
