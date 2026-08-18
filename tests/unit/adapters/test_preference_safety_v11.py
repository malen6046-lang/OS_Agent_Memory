"""Contract tests for adapters over the immutable Algorithm V1.1 code."""

from __future__ import annotations

import hashlib
import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from adapters.preference_safety.errors import (
    ConfirmationExpiredError,
    ConfirmationInvalidError,
    ForgetAuthorizationError,
    ForgetSelectionError,
)
from adapters.preference_safety.forget import (
    ForgetServiceAdapter,
    build_forget_service,
)
from adapters.preference_safety.preference import (
    PreferenceServiceAdapter,
    build_preference_service,
)
from adapters.preference_safety.safety import (
    SafetyServiceAdapter,
    build_safety_service,
)
from contracts.schemas.envelope import Envelope
from contracts.schemas.common import MemoryStatus, PreferenceScope
from contracts.schemas.forget import (
    ForgetExecuteRequest,
    ForgetExecutionPlan,
    ForgetPlan,
    ForgetPreviewRequest,
)
from contracts.schemas.preference import PreferenceCandidate, PreferenceRecord
from contracts.schemas.retrieval import SearchHit, SearchResponse
from contracts.schemas.safety import SafetyCheckResult


NOW = datetime(2099, 8, 5, 12, 0, tzinfo=timezone.utc)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
LEGACY_ROOT = (
    PROJECT_ROOT / "modules" / "preference_safety" / "algorithm_v1_1"
)
EXPECTED_LEGACY_BLOBS = {
    "preference_service.py": "5b8e332de6940b79a73bd4f9bd3a4365a3242d11",
    "safety_service.py": "1aebf2ff4a8b2058f0a96da5221f437d39ccd1f5",
    "forget_service.py": "cbbf2666d3335028e711e3ed0f8821e8f099b93a",
}


def _envelope(text: str = "我喜欢深色主题") -> Envelope:
    return Envelope(
        contract_version="1.0",
        request_id="req_adapter",
        idempotency_key="idem_adapter",
        user_id="usr_1",
        scene="desktop",
        source="tool_result",
        source_event_id="evt_adapter",
        occurred_at=NOW,
        payload={"nested": {"text": text}},
    )


def _git_blob_id(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def test_algorithm_v11_sources_are_byte_for_byte_immutable():
    assert {
        name: _git_blob_id(LEGACY_ROOT / name)
        for name in EXPECTED_LEGACY_BLOBS
    } == EXPECTED_LEGACY_BLOBS


def test_factories_return_synchronous_contract_adapters():
    preference = build_preference_service()
    safety = build_safety_service()
    forget = build_forget_service()

    assert isinstance(preference, PreferenceServiceAdapter)
    assert isinstance(safety, SafetyServiceAdapter)
    assert isinstance(forget, ForgetServiceAdapter)
    for method in (
        preference.extract,
        preference.upsert,
        preference.resolve,
        preference.history,
        safety.check,
        forget.preview,
        forget.execute,
    ):
        assert not inspect.iscoroutinefunction(method)


class PreferenceLegacySpy:
    def __init__(self) -> None:
        self.calls = []

    def extract(self, events):
        self.calls.append(("extract", events))
        event = events[0]
        return [
            {
                "user_id": event["user_id"],
                "preference_key": "theme",
                "value": "dark",
                "category": "ui",
                "scope": "global",
                "scene": event["scene"],
                "confidence": 0.9,
                "source_event_id": event["source_event_id"],
            }
        ]

    def upsert(self, candidates):
        self.calls.append(("upsert", candidates))
        candidate = candidates[0]
        return [
            {
                **candidate,
                "evidence_count": 1,
                "evidence": [
                    {
                        "source_event_id": candidate["source_event_id"],
                        "weight": candidate["confidence"],
                    }
                ],
                "revision": 1,
                "status": "active",
            }
        ]

    def resolve(self, user_id, scene, keys=None):
        self.calls.append(("resolve", user_id, scene, keys))
        return [self._record(user_id)]

    def history(self, user_id, preference_key):
        self.calls.append(("history", user_id, preference_key))
        return [self._record(user_id)]

    @staticmethod
    def _record(user_id):
        return {
            "user_id": user_id,
            "preference_key": "theme",
            "value": "dark",
            "category": "ui",
            "scope": "global",
            "scope_value": "desktop",
            "polarity": "positive",
            "confidence": 0.9,
            "evidence_count": 1,
            "evidence": [
                {"source_event_id": "evt_adapter", "weight": 0.9}
            ],
            "revision": 1,
            "status": "active",
        }


def test_preference_adapter_calls_all_raw_methods_and_maps_models():
    legacy = PreferenceLegacySpy()
    service = PreferenceServiceAdapter(legacy)

    candidates = service.extract([_envelope()])
    records = service.upsert(candidates)
    resolved = service.resolve("usr_1", "desktop", ["theme"])
    history = service.history("usr_1", "theme")

    assert all(isinstance(item, PreferenceCandidate) for item in candidates)
    assert all(isinstance(item, PreferenceRecord) for item in records)
    assert all(isinstance(item, PreferenceRecord) for item in resolved)
    assert all(isinstance(item, PreferenceRecord) for item in history)
    raw_event = legacy.calls[0][1][0]
    assert raw_event["text"] == "我喜欢深色主题"
    assert raw_event["user_id"] == "usr_1"
    assert raw_event["source_event_id"] == "evt_adapter"
    assert [call[0] for call in legacy.calls] == [
        "extract",
        "upsert",
        "resolve",
        "history",
    ]
    assert "user_id" not in records[0].model_dump()


def test_preference_factory_runs_the_real_legacy_methods():
    service = build_preference_service()

    candidates = service.extract([_envelope()])
    theme = next(
        item for item in candidates if item.preference_key == "theme"
    )
    record = service.upsert([theme])[0]

    assert isinstance(theme, PreferenceCandidate)
    assert isinstance(record, PreferenceRecord)
    assert record.value == "dark"
    assert service.resolve("usr_1", "desktop", ["theme"])[0].value == "dark"
    assert service.history("usr_1", "theme")[0].revision == 1


def _preference_candidate(
    value: str,
    scope: PreferenceScope,
    scope_value: str,
) -> PreferenceCandidate:
    return PreferenceCandidate(
        user_id="usr_scope",
        preference_key="editor.theme",
        value=value,
        category="editor",
        scope=scope,
        scope_value=scope_value,
        polarity="positive",
        confidence=0.9,
        evidence=[{"source_event_id": f"evt_{scope.value}_{scope_value}"}],
    )


def test_preference_state_is_partitioned_by_user_scope_and_scope_value():
    service = build_preference_service()
    service.upsert(
        [
            _preference_candidate("dark", PreferenceScope.GLOBAL, "ignored"),
            _preference_candidate("light", PreferenceScope.SCENE, "office"),
            _preference_candidate("blue", PreferenceScope.SCENE, "meeting"),
            _preference_candidate("vim", PreferenceScope.TOOL, "editor"),
        ]
    )

    assert service.resolve("usr_scope", "office", ["editor.theme"])[0].value == "light"
    assert service.resolve("usr_scope", "meeting", ["editor.theme"])[0].value == "blue"
    assert service.resolve("usr_scope", "other", ["editor.theme"])[0].value == "dark"
    assert service.resolve("usr_scope", "editor", ["editor.theme"])[0].value == "dark"
    assert len(service.history("usr_scope", "editor.theme")) == 4


class SafetyLegacySpy:
    def __init__(self) -> None:
        self.text = None

    def check(self, text):
        self.text = text
        return {
            "has_sensitive": True,
            "block": True,
            "entities": [
                {
                    "type": "phone",
                    "value": "138*****678",
                    "masked_value": "138*****678",
                    "start": 6,
                    "end": 17,
                }
            ],
        }


def test_safety_adapter_calls_raw_check_and_drops_sensitive_details():
    legacy = SafetyLegacySpy()
    service = SafetyServiceAdapter(legacy)
    secret = "13812345678"

    result = service.check(_envelope(f"联系电话 {secret}"))

    assert isinstance(result, SafetyCheckResult)
    assert legacy.text == f"联系电话 {secret}"
    assert result == SafetyCheckResult(
        allowed=False,
        reason_codes=["sensitive.phone"],
        entity_types=["phone"],
    )
    serialized = result.model_dump_json()
    assert secret not in serialized
    assert "138*****678" not in serialized


class ForgetLegacySpy:
    def __init__(self) -> None:
        self.preview_calls = []
        self.execute_calls = 0

    def preview(
        self,
        instruction,
        retriever=None,
        user_id="",
        metadata_store=None,
    ):
        self.preview_calls.append(
            (instruction, retriever, user_id, metadata_store)
        )
        items = (
            retriever.search(
                {"query": "终端", "user_id": user_id, "top_k": 20}
            )["items"]
            if retriever is not None
            else []
        )
        return {
            "candidates": items,
            "risk_level": "low",
            "confirmation_token": "legacy_token_must_be_ignored",
        }

    def execute(self, *_args, **_kwargs):
        self.execute_calls += 1
        raise AssertionError("the adapter must never call legacy execute")


def _forget_service(legacy, clock):
    return ForgetServiceAdapter(
        legacy_factory=lambda: legacy,
        candidate_resolver=lambda user_id, _keyword: [
            {"memory_id": "mem_algorithm", "user_id": user_id, "score": 0.9},
            {"memory_id": "mem_foreign", "user_id": "usr_other"},
        ],
        clock=clock,
        token_factory=lambda: "confirm_adapter_token",
        plan_id_factory=lambda: "plan_adapter_1",
    )


def test_forget_adapter_calls_only_raw_preview_and_owns_safe_execution():
    current = [NOW]
    legacy = ForgetLegacySpy()
    service = _forget_service(legacy, lambda: current[0])
    plan = service.preview(
        ForgetPreviewRequest(
            request_id="req_preview",
            user_id="usr_1",
            instruction="忘记关于终端的记忆",
            memory_ids=["mem_explicit"],
        )
    )

    assert isinstance(plan, ForgetPlan)
    assert [item.memory_id for item in plan.candidates] == [
        "mem_explicit",
        "mem_algorithm",
    ]
    assert plan.confirmation_token == "confirm_adapter_token"
    assert plan.confirmation_token != "legacy_token_must_be_ignored"
    assert legacy.preview_calls[0][0] == "忘记关于终端的记忆"
    assert legacy.preview_calls[0][2:] == ("usr_1", None)

    request = ForgetExecuteRequest(
        request_id="req_execute",
        user_id="usr_1",
        plan_id=plan.plan_id,
        confirmation_token=plan.confirmation_token,
        selected_ids=["mem_algorithm"],
    )
    first = service.execute(request)
    replay = service.execute(request)

    assert isinstance(first, ForgetExecutionPlan)
    assert replay == first
    assert first.memory_ids == ["mem_algorithm"]
    assert legacy.execute_calls == 0


def test_forget_adapter_enforces_token_authorization_selection_and_expiry():
    current = [NOW]
    legacy = ForgetLegacySpy()
    service = _forget_service(legacy, lambda: current[0])
    plan = service.preview(
        ForgetPreviewRequest(
            request_id="req_preview",
            user_id="usr_1",
            memory_ids=["mem_1"],
        )
    )

    def request(**changes):
        data = {
            "request_id": "req_execute",
            "user_id": "usr_1",
            "plan_id": plan.plan_id,
            "confirmation_token": plan.confirmation_token,
            "selected_ids": ["mem_1"],
        }
        data.update(changes)
        return ForgetExecuteRequest(**data)

    with pytest.raises(ConfirmationInvalidError):
        service.execute(request(confirmation_token="confirm_wrong"))
    with pytest.raises(ForgetAuthorizationError):
        service.execute(request(user_id="usr_other"))
    with pytest.raises(ConfirmationInvalidError):
        service.execute(request(plan_id="plan_wrong"))
    with pytest.raises(ForgetSelectionError):
        service.execute(request(selected_ids=["mem_other"]))

    current[0] += timedelta(minutes=5)
    with pytest.raises(ConfirmationExpiredError):
        service.execute(request())
    assert legacy.execute_calls == 0


class FrozenRetrieverSpy:
    def __init__(self) -> None:
        self.requests = []

    def search(self, request):
        self.requests.append(request)
        return SearchResponse(
            request_id=request.request_id,
            user_id=request.user_id,
            items=[
                SearchHit(
                    memory_id="mem_owned",
                    user_id=request.user_id,
                    status=MemoryStatus.ACTIVE,
                    content_text="terminal settings",
                    score=0.9,
                ),
                SearchHit(
                    memory_id="mem_foreign",
                    user_id="usr_other",
                    status=MemoryStatus.ACTIVE,
                    content_text="foreign terminal settings",
                    score=0.8,
                ),
                SearchHit(
                    memory_id="mem_deleted",
                    user_id=request.user_id,
                    status=MemoryStatus.TOMBSTONED,
                    content_text="old terminal settings",
                    score=0.7,
                ),
            ],
            total=3,
            provider="test",
        )


def test_forget_factory_bridges_frozen_retriever_into_legacy_preview():
    retriever = FrozenRetrieverSpy()
    service = build_forget_service(
        retriever=retriever,
        config=object(),
        app_config=object(),
    )

    plan = service.preview(
        ForgetPreviewRequest(
            request_id="req_preview_retriever",
            user_id="usr_1",
            instruction="terminal",
        )
    )

    assert len(retriever.requests) == 1
    assert retriever.requests[0].user_id == "usr_1"
    assert retriever.requests[0].query == "terminal"
    assert retriever.requests[0].top_k == 20
    assert [candidate.memory_id for candidate in plan.candidates] == [
        "mem_owned"
    ]
