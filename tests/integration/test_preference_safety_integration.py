"""End-to-end gate for the staged preference_safety profile."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import ConfigManager
from app.dependencies import build_service_container, get_memory_orchestrator
from adapters.preference_safety.forget import ForgetServiceAdapter
from contracts.schemas.envelope import Envelope
from contracts.schemas.forget import ForgetExecuteRequest, ForgetPreviewRequest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _envelope(event_id: str, text: str) -> Envelope:
    return Envelope(
        contract_version="1.0",
        request_id=f"req_{event_id}",
        idempotency_key=f"idem_{event_id}",
        user_id="usr_pref_safety",
        scene="desktop",
        source="user_behavior",
        source_event_id=event_id,
        occurred_at=datetime.now(timezone.utc),
        payload={"text": text},
    )


@pytest.mark.anyio
async def test_profile_runs_real_preference_safety_and_two_stage_forget():
    container = build_service_container(
        ConfigManager().load("preference_safety")
    )
    orchestrator = get_memory_orchestrator(container)
    await container.start()
    try:
        ingested = await orchestrator.ingest(
            _envelope("evt_safe", "I use vim for daily editing.")
        )

        assert ingested["success"] is True
        preferences = ingested["data"]["preference_result"]
        assert [(item["preference_key"], item["value"]) for item in preferences] == [
            ("tool.editor", "vim")
        ]
        records = ingested["data"]["repository_result"]["records"]
        memory_id = records[0]["memory_id"]

        previewed = await orchestrator.preview_forget(
            ForgetPreviewRequest(
                request_id="req_preview",
                user_id="usr_pref_safety",
                memory_ids=[memory_id],
                reason="user request",
            )
        )
        plan = previewed["data"]
        assert previewed["success"] is True
        assert [item["memory_id"] for item in plan["candidates"]] == [
            memory_id
        ]

        invalid_selection = await orchestrator.execute_forget(
            ForgetExecuteRequest(
                request_id="req_invalid_selection",
                user_id="usr_pref_safety",
                plan_id=plan["plan_id"],
                confirmation_token=plan["confirmation_token"],
                selected_ids=["mem_not_previewed"],
            )
        )
        assert invalid_selection["success"] is False
        assert invalid_selection["error"]["code"] == "VALIDATION_ERROR"

        unauthorized = await orchestrator.execute_forget(
            ForgetExecuteRequest(
                request_id="req_unauthorized",
                user_id="usr_other",
                plan_id=plan["plan_id"],
                confirmation_token=plan["confirmation_token"],
                selected_ids=[memory_id],
            )
        )
        assert unauthorized["success"] is False
        assert unauthorized["error"]["code"] == "UNAUTHORIZED_SCOPE"

        execute_request = ForgetExecuteRequest(
            request_id="req_execute",
            user_id="usr_pref_safety",
            plan_id=plan["plan_id"],
            confirmation_token=plan["confirmation_token"],
            selected_ids=[memory_id],
        )
        concurrent_results = await asyncio.gather(
            orchestrator.execute_forget(execute_request),
            orchestrator.execute_forget(execute_request),
        )
        forgotten = next(
            result
            for result in concurrent_results
            if not result["meta"]["idempotent_replay"]
        )
        concurrent_replay = next(
            result
            for result in concurrent_results
            if result["meta"]["idempotent_replay"]
        )

        assert forgotten["success"] is True
        assert concurrent_replay["success"] is True
        assert forgotten["data"]["forget_result"]["memory_ids"] == [
            memory_id
        ]
        stored = container.memory_repository.records[memory_id]
        assert stored.status.value == "tombstoned"
        revision = stored.revision
        audit_count = len(container.audit_repository.events)

        replayed = await orchestrator.execute_forget(execute_request)

        assert replayed["success"] is True
        assert replayed["meta"]["idempotent_replay"] is True
        assert (
            container.memory_repository.records[memory_id].revision
            == revision
        )
        assert len(container.audit_repository.events) == audit_count
        forget_keys = [
            key
            for (_user, operation, key) in (
                container.idempotency_repository.entries
            )
            if operation == "forget.execute"
        ]
        assert len(forget_keys) == 1
        assert forget_keys[0].startswith("__forget_execute__:")
        assert plan["confirmation_token"] not in forget_keys[0]
    finally:
        await container.close()


@pytest.mark.anyio
async def test_real_safety_blocks_sensitive_payload_before_any_write():
    container = build_service_container(
        ConfigManager().load("preference_safety")
    )
    orchestrator = get_memory_orchestrator(container)
    await container.start()
    try:
        blocked = await orchestrator.ingest(
            _envelope("evt_sensitive", "phone=13812345678")
        )

        assert blocked["success"] is False
        assert blocked["error"]["code"] == "SENSITIVE_CONTENT_BLOCKED"
        assert container.memory_repository.records == {}
        assert container.audit_repository.events == []
        assert "13812345678" not in str(blocked)
    finally:
        await container.close()


@pytest.mark.anyio
async def test_expired_confirmation_uses_the_frozen_error_code():
    current = [datetime(2099, 1, 1, tzinfo=timezone.utc)]
    forget_service = ForgetServiceAdapter(clock=lambda: current[0])
    container = build_service_container(
        ConfigManager().load("preference_safety")
    )
    container.forget_service = forget_service
    orchestrator = get_memory_orchestrator(container)
    plan = forget_service.preview(
        ForgetPreviewRequest(
            request_id="req_expiry_preview",
            user_id="usr_pref_safety",
            memory_ids=["mem_expiring"],
        )
    )
    current[0] += timedelta(minutes=6)

    result = await orchestrator.execute_forget(
        ForgetExecuteRequest(
            request_id="req_expired",
            user_id="usr_pref_safety",
            plan_id=plan.plan_id,
            confirmation_token=plan.confirmation_token,
            selected_ids=["mem_expiring"],
        )
    )

    assert result["success"] is False
    assert result["error"]["code"] == "CONFIRMATION_EXPIRED"
    assert plan.confirmation_token not in str(result)
