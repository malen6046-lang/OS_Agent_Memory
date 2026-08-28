"""Regression tests for the V1.2 working/episodic/semantic flow."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.core.config import ConfigManager
from app.dependencies import build_service_container, get_memory_orchestrator
from contracts.schemas.envelope import Envelope
from contracts.schemas.retrieval import SearchRequest
from modules.knowledge_retrieval.memory_flow_v1_2 import (
    MemoryFlowController,
    MemoryFlowTier,
)


def test_repeated_access_promotes_working_to_episodic_to_semantic() -> None:
    flow = MemoryFlowController()
    state = flow.register("mem_1", "usr_1", importance=0.7)

    assert state.tier is MemoryFlowTier.WORKING
    for _ in range(3):
        state = flow.observe_access("mem_1", "usr_1")
        assert state is not None
    assert state.tier is MemoryFlowTier.EPISODIC

    for _ in range(3):
        state = flow.observe_access("mem_1", "usr_1")
        assert state is not None
    assert state.tier is MemoryFlowTier.SEMANTIC


def test_manual_or_pinned_memory_starts_semantic() -> None:
    flow = MemoryFlowController()
    state = flow.register(
        "mem_manual",
        "usr_1",
        importance=0.4,
        pinned=True,
    )

    assert state.tier is MemoryFlowTier.SEMANTIC


def test_flow_never_crosses_user_scope_and_remove_deactivates() -> None:
    flow = MemoryFlowController()
    flow.register("mem_1", "usr_1", importance=0.5)

    assert flow.observe_access("mem_1", "usr_other") is None
    assert flow.snapshot("mem_1", "usr_other") is None
    assert flow.remove("mem_1") is True
    assert flow.observe_access("mem_1", "usr_1") is None


@pytest.mark.anyio
async def test_algorithm_search_exposes_live_tier_promotions() -> None:
    container = build_service_container(
        ConfigManager().load("algorithm_modules")
    )
    orchestrator = get_memory_orchestrator(container)
    await container.start()
    try:
        ingested = await orchestrator.ingest(
            Envelope(
                contract_version="1.0",
                request_id="req_flow_ingest",
                idempotency_key="idem_flow_ingest",
                user_id="usr_flow",
                scene="desktop",
                source="user_behavior",
                source_event_id="evt_flow_ingest",
                occurred_at=datetime.now(timezone.utc),
                payload={
                    "text": "桌面默认采用海蓝色背景",
                    "importance": 0.7,
                },
            )
        )
        record = ingested["data"]["repository_result"]["records"][0]
        assert record["attributes"]["memory_tier"] == "working"

        observed: list[str] = []
        for index in range(6):
            searched = await orchestrator.search(
                SearchRequest(
                    request_id=f"req_flow_search_{index}",
                    user_id="usr_flow",
                    query="海蓝色背景",
                    top_k=1,
                )
            )
            assert searched["success"] is True
            observed.append(
                searched["data"]["items"][0]["attributes"][
                    "memory_tier"
                ]
            )

        assert observed[0] == "working"
        assert observed[2] == "episodic"
        assert observed[5] == "semantic"
    finally:
        await container.close()
