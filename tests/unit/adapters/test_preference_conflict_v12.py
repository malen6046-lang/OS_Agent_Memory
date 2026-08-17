"""Regression tests for contract-aligned preference/conflict algorithms."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from adapters.knowledge_retrieval.knowledge import KnowledgeServiceAdapter
from adapters.preference_safety.preference import PreferenceServiceAdapter
from contracts.schemas.envelope import Envelope
from contracts.schemas.memory import MemoryRecord


NOW = datetime(2026, 8, 14, 9, 0, tzinfo=timezone.utc)


class _Embedding:
    def health(self, deep: bool = False):
        del deep
        return {"provider": "test", "status": "ok", "details": {}}

    def model_info(self):
        return {"provider": "test", "model_name": "unused", "dimension": 1}

    def encode(self, texts):
        return {
            "vectors": [[0.0] for _ in texts],
            "model_name": "unused",
            "dimension": 1,
        }


class _VectorStore:
    def query(self, request):
        del request
        return []


def _event(
    text: str,
    *,
    scene: str = "desktop",
    source_event_id: str = "evt_pref",
) -> Envelope:
    return Envelope(
        contract_version="1.0",
        request_id=f"req_{source_event_id}",
        idempotency_key=f"idem_{source_event_id}",
        user_id="usr_pref",
        session_id=None,
        scene=scene,
        source="user_behavior",
        source_event_id=source_event_id,
        occurred_at=NOW,
        payload={"text": text},
    )


def _record(
    memory_id: str,
    key: str,
    value: str,
    text: str,
    *,
    subtype: str = "operation_habit",
    valid_from: datetime = NOW,
    user_id: str = "usr_conflict",
) -> MemoryRecord:
    return MemoryRecord(
        memory_id=memory_id,
        user_id=user_id,
        memory_kind="preference",
        subtype=subtype,
        content_text=text,
        content={"preference_key": key, "value": value},
        status="active",
        confidence=0.9,
        importance=0.7,
        revision=1,
        valid_from=valid_from,
        scene_tags=["desktop"],
        source_refs=[f"evt_{memory_id}"],
        supersedes=[],
        attributes={},
    )


def _preference_signatures(text: str, *, scene: str = "desktop") -> set[tuple]:
    candidates = PreferenceServiceAdapter().extract([_event(text, scene=scene)])
    return {
        (
            candidate.preference_key,
            candidate.value,
            candidate.category,
            candidate.scope.value,
            candidate.scope_value,
        )
        for candidate in candidates
    }


def test_preference_extraction_normalizes_legacy_contract_fields() -> None:
    assert _preference_signatures("我日常用 vim，并喜欢深色主题") == {
        ("tool.editor", "vim", "tool_choice", "global", "global"),
        ("ui.theme", "dark", "operation_habit", "global", "global"),
    }


def test_preference_extraction_supports_multiple_contextual_preferences() -> None:
    assert _preference_signatures(
        "办公用 WPS，周报用 Markdown，纪要先写结论再附表格"
    ) == {
        ("tool.office", "wps", "tool_choice", "global", "global"),
        ("output.format", "markdown", "output_style", "global", "global"),
        (
            "output.structure",
            "conclusion_then_table",
            "output_style",
            "global",
            "global",
        ),
    }


@pytest.mark.parametrize(
    "text",
    (
        "这次临时使用深色主题，下次不用管",
        "演示这一小时先关掉自动锁屏",
    ),
)
def test_preference_extraction_rejects_temporary_instructions(text: str) -> None:
    assert _preference_signatures(text) == set()


def test_preference_extraction_preserves_scene_scope() -> None:
    assert _preference_signatures(
        "交付场景使用公司 HTTP 代理",
        scene="delivery",
    ) == {
        (
            "network.proxy",
            "corp_http",
            "operation_habit",
            "scene",
            "delivery",
        )
    }


@pytest.fixture
def conflict_service() -> KnowledgeServiceAdapter:
    return KnowledgeServiceAdapter(_Embedding(), _VectorStore())


def test_conflict_same_slot_and_value_is_duplicate(
    conflict_service: KnowledgeServiceAdapter,
) -> None:
    old = _record("mem_old", "ui.theme", "dark", "用户喜欢深色主题")
    new = _record(
        "mem_new",
        "ui.theme",
        "dark",
        "界面偏好为暗色",
        valid_from=NOW + timedelta(days=1),
    )

    decision = conflict_service.classify_conflict(old, new)

    assert (decision.relation, decision.strategy) == (
        "duplicate",
        "keep_old",
    )


def test_conflict_same_value_with_new_evidence_is_support(
    conflict_service: KnowledgeServiceAdapter,
) -> None:
    old = _record(
        "mem_old",
        "workflow.backup",
        "incremental_local",
        "增量备份到本地盘",
    )
    new = _record(
        "mem_new",
        "workflow.backup",
        "incremental_local",
        "备份成功日志确认本地盘可用",
        valid_from=NOW + timedelta(days=1),
    )

    decision = conflict_service.classify_conflict(old, new)

    assert (decision.relation, decision.strategy) == ("support", "merge")


def test_conflict_extension_is_classified_before_newer_replacement(
    conflict_service: KnowledgeServiceAdapter,
) -> None:
    old = _record(
        "mem_old",
        "output.structure",
        "conclusion",
        "纪要包含结论",
    )
    new = _record(
        "mem_new",
        "output.structure",
        "conclusion_and_todos",
        "纪要还需要待办列表",
        valid_from=NOW + timedelta(days=1),
    )

    decision = conflict_service.classify_conflict(old, new)

    assert (decision.relation, decision.strategy) == ("extend", "merge")


def test_security_conflict_uses_manual_review_for_scene_exception(
    conflict_service: KnowledgeServiceAdapter,
) -> None:
    old = _record(
        "mem_old",
        "security.debug_port",
        "8080",
        "允许调试端口 8080",
        subtype="security_policy",
    )
    new = _record(
        "mem_new",
        "security.debug_port",
        "disabled",
        "交付场景禁止调试端口",
        subtype="security_policy",
        valid_from=NOW + timedelta(days=1),
    )

    decision = conflict_service.classify_conflict(old, new)

    assert (decision.relation, decision.strategy) == (
        "contradict",
        "manual_review",
    )


def test_value_outside_known_slot_domain_is_unrelated(
    conflict_service: KnowledgeServiceAdapter,
) -> None:
    old = _record("mem_old", "tool.browser", "firefox", "默认 Firefox")
    new = _record(
        "mem_new",
        "tool.browser",
        "pubkey_only",
        "SSH 仅允许密钥登录",
        valid_from=NOW + timedelta(days=1),
    )

    decision = conflict_service.classify_conflict(old, new)

    assert (decision.relation, decision.strategy) == (
        "unrelated",
        "keep_old",
    )


def test_different_users_never_conflict(
    conflict_service: KnowledgeServiceAdapter,
) -> None:
    old = _record("mem_old", "ui.theme", "dark", "深色主题")
    new = _record(
        "mem_new",
        "ui.theme",
        "light",
        "浅色主题",
        user_id="usr_other",
        valid_from=NOW + timedelta(days=1),
    )

    decision = conflict_service.classify_conflict(old, new)

    assert (decision.relation, decision.strategy) == (
        "unrelated",
        "keep_old",
    )
