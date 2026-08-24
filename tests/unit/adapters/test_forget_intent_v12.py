"""Regression tests for precise V1.2 forget intent handling."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from adapters.preference_safety.forget import ForgetServiceAdapter
from app.core.config import ConfigManager
from app.dependencies import build_service_container, get_memory_orchestrator
from contracts.schemas.envelope import Envelope
from contracts.schemas.forget import ForgetPreviewRequest
from modules.preference_safety.forget_intent_v1_2 import (
    parse_forget_intent,
    select_relevant_candidates,
)


def test_parser_separates_target_and_explicit_keep_clause() -> None:
    intent = parse_forget_intent(
        "忘记星河专项会议细节，保留纪要排版习惯"
    )

    assert intent.scope == "topic"
    assert intent.target == "星河专项会议细节"
    assert intent.exclusions == ("纪要排版习惯",)
    assert intent.resolver_query == "星河专项会议细节"


def test_parser_distinguishes_all_from_bounded_all() -> None:
    everything = parse_forget_intent("忘记全部记忆")
    temporary = parse_forget_intent("清除所有临时记忆")

    assert everything.resolver_query == "__all__"
    assert temporary.resolver_query == "__all__:临时"


def test_reranker_rejects_high_scoring_but_lexically_unrelated_items() -> None:
    selected = select_relevant_candidates(
        "深色主题",
        [
            {
                "memory_id": "mem_theme",
                "content_text": "桌面默认使用深色主题",
                "score": 0.62,
            },
            {
                "memory_id": "mem_backup",
                "content_text": "每周执行增量备份",
                "score": 0.94,
            },
        ],
    )

    assert [item["memory_id"] for item in selected] == ["mem_theme"]


def test_reranker_abstains_when_dense_scores_are_ambiguous() -> None:
    selected = select_relevant_candidates(
        "蓝牙配对",
        [
            {
                "memory_id": "mem_theme",
                "content_text": "桌面主题",
                "score": 0.84,
            },
            {
                "memory_id": "mem_backup",
                "content_text": "备份策略",
                "score": 0.82,
            },
        ],
    )

    assert selected == []


def test_keep_clause_filters_trusted_custom_resolver_candidates() -> None:
    calls: list[tuple[str, str]] = []

    def resolver(user_id: str, query: str):
        calls.append((user_id, query))
        return [
            {
                "memory_id": "mem_project",
                "user_id": user_id,
                "content_text": "星河专项会议讨论细节",
            },
            {
                "memory_id": "mem_style",
                "user_id": user_id,
                "content_text": "纪要排版习惯使用表格",
            },
        ]

    service = ForgetServiceAdapter(candidate_resolver=resolver)
    plan = service.preview(
        ForgetPreviewRequest(
            request_id="req_keep_clause",
            user_id="usr_1",
            instruction="忘记星河专项会议细节，保留纪要排版习惯",
        )
    )

    assert calls == [("usr_1", "星河专项会议细节")]
    assert [item.memory_id for item in plan.candidates] == ["mem_project"]
    assert plan.risk_level == "medium"


def test_all_and_bounded_all_use_explicit_active_enumeration() -> None:
    class Retriever:
        def search(self, _request):
            raise AssertionError("all-scope preview must not issue similarity search")

        def list_active_candidates(self, user_id: str):
            return [
                {
                    "memory_id": "mem_temp",
                    "user_id": user_id,
                    "content_text": "临时会话草稿",
                },
                {
                    "memory_id": "mem_stable",
                    "user_id": user_id,
                    "content_text": "长期使用深色主题",
                },
            ]

    from adapters.preference_safety.forget import build_forget_service

    service = build_forget_service(retriever=Retriever())
    bounded = service.preview(
        ForgetPreviewRequest(
            request_id="req_all_temp",
            user_id="usr_1",
            instruction="忘记全部临时记忆",
        )
    )
    everything = service.preview(
        ForgetPreviewRequest(
            request_id="req_all",
            user_id="usr_1",
            instruction="忘记全部记忆",
        )
    )

    assert [item.memory_id for item in bounded.candidates] == ["mem_temp"]
    assert bounded.risk_level == "medium"
    assert {item.memory_id for item in everything.candidates} == {
        "mem_temp",
        "mem_stable",
    }
    assert everything.risk_level == "high"


def test_sensitive_forget_target_is_always_high_risk() -> None:
    service = ForgetServiceAdapter(
        candidate_resolver=lambda user_id, _query: [
            {"memory_id": "mem_secret", "user_id": user_id}
        ]
    )

    plan = service.preview(
        ForgetPreviewRequest(
            request_id="req_secret",
            user_id="usr_1",
            instruction="忘记密码相关记忆",
        )
    )

    assert plan.risk_level == "high"


@pytest.mark.anyio
async def test_algorithm_container_enumerates_all_and_bounded_all() -> None:
    container = build_service_container(
        ConfigManager().load("algorithm_modules")
    )
    orchestrator = get_memory_orchestrator(container)
    await container.start()
    try:
        for index, text in enumerate(
            ("临时会话草稿", "长期使用深色主题"),
            start=1,
        ):
            ingested = await orchestrator.ingest(
                Envelope(
                    contract_version="1.0",
                    request_id=f"req_forget_all_{index}",
                    idempotency_key=f"idem_forget_all_{index}",
                    user_id="usr_forget_all",
                    scene="desktop",
                    source="user_behavior",
                    source_event_id=f"evt_forget_all_{index}",
                    occurred_at=datetime.now(timezone.utc),
                    payload={"text": text},
                )
            )
            assert ingested["success"] is True

        bounded = await orchestrator.preview_forget(
            ForgetPreviewRequest(
                request_id="req_preview_all_temp",
                user_id="usr_forget_all",
                instruction="忘记全部临时记忆",
            )
        )
        everything = await orchestrator.preview_forget(
            ForgetPreviewRequest(
                request_id="req_preview_all",
                user_id="usr_forget_all",
                instruction="忘记全部记忆",
            )
        )

        assert bounded["success"] is True
        assert len(bounded["data"]["candidates"]) == 1
        assert bounded["data"]["risk_level"] == "medium"
        assert everything["success"] is True
        assert len(everything["data"]["candidates"]) == 2
        assert everything["data"]["risk_level"] == "high"
    finally:
        await container.close()
