"""Acceptance tests for two-stage forget planning and validation."""

from __future__ import annotations

import inspect
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from contracts.schemas.forget import (
    ForgetCandidate,
    ForgetExecuteRequest,
    ForgetExecutionPlan,
    ForgetPlan,
    ForgetPreviewRequest,
)
from modules.preference_safety import ForgetService
from modules.preference_safety.errors import (
    ConfirmationExpiredError,
    ConfirmationInvalidError,
    ForgetAuthorizationError,
    ForgetSelectionError,
)


NOW = datetime(2099, 8, 5, 12, 0, tzinfo=timezone.utc)


class MutableClock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


def _service(
    *,
    clock: MutableClock | None = None,
    resolver=None,
) -> ForgetService:
    return ForgetService(
        ttl_seconds=300,
        candidate_resolver=resolver,
        clock=clock or MutableClock(),
        token_factory=lambda: "confirm_contract_token",
        plan_id_factory=lambda: "plan_contract_1",
    )


def _preview(
    service: ForgetService,
    *,
    user_id: str = "usr_1",
    memory_ids: list[str] | None = None,
    instruction: str | None = None,
) -> ForgetPlan:
    return service.preview(
        ForgetPreviewRequest(
            request_id="req_preview",
            user_id=user_id,
            memory_ids=memory_ids or [],
            instruction=instruction,
        )
    )


def _execute_request(
    plan: ForgetPlan,
    *,
    request_id: str = "req_execute",
    user_id: str | None = None,
    plan_id: str | None = None,
    token: str | None = None,
    selected_ids: list[str] | None = None,
) -> ForgetExecuteRequest:
    return ForgetExecuteRequest(
        request_id=request_id,
        user_id=user_id or plan.user_id,
        plan_id=plan_id or plan.plan_id,
        confirmation_token=token or plan.confirmation_token,
        selected_ids=selected_ids or [
            candidate.memory_id for candidate in plan.candidates
        ],
    )


def test_public_methods_keep_frozen_synchronous_request_only_signatures():
    for method_name in ("preview", "execute"):
        method = getattr(ForgetService, method_name)
        assert not inspect.iscoroutinefunction(method)
        assert list(inspect.signature(method).parameters) == [
            "self",
            "request",
        ]


def test_preview_and_execute_return_frozen_contract_models():
    clock = MutableClock()
    service = _service(clock=clock)
    plan = _preview(service, memory_ids=["mem_1", "mem_1", "mem_2"])

    assert isinstance(plan, ForgetPlan)
    assert all(isinstance(item, ForgetCandidate) for item in plan.candidates)
    assert [item.memory_id for item in plan.candidates] == ["mem_1", "mem_2"]
    assert all(item.user_id == "usr_1" for item in plan.candidates)
    assert plan.requires_confirmation is True
    assert plan.expires_at == NOW + timedelta(seconds=300)
    assert plan.expires_at.tzinfo is not None

    execution = service.execute(
        _execute_request(plan, selected_ids=["mem_2", "mem_1", "mem_2"])
    )
    assert isinstance(execution, ForgetExecutionPlan)
    assert execution.request_id == "req_execute"
    assert execution.user_id == "usr_1"
    assert execution.plan_id == plan.plan_id
    assert execution.memory_ids == ["mem_2", "mem_1"]
    assert execution.expires_at == plan.expires_at


def test_instruction_parser_resolver_is_user_scoped_and_does_not_mutate_input():
    calls = []
    local = {"memory_id": "mem_local", "user_id": "usr_1"}
    foreign = {"memory_id": "mem_foreign", "user_id": "usr_2"}
    source = [local, "mem_local", foreign]
    before = deepcopy(source)

    def resolver(user_id, keyword):
        calls.append((user_id, keyword))
        return source

    plan = _preview(
        _service(resolver=resolver),
        instruction="忘记关于终端快捷键的记忆",
    )

    assert calls == [("usr_1", "终端快捷键")]
    assert [item.memory_id for item in plan.candidates] == ["mem_local"]
    assert source == before


def test_duplicate_candidates_preserve_the_highest_risk():
    def resolver(_user_id, _keyword):
        return [
            {
                "memory_id": "mem_1",
                "user_id": "usr_1",
                "risk_level": "high",
            }
        ]

    plan = _preview(
        _service(resolver=resolver),
        memory_ids=["mem_1"],
        instruction="忘记终端",
    )

    assert len(plan.candidates) == 1
    assert plan.candidates[0].risk_level == "high"


@pytest.mark.parametrize(
    ("memory_count", "instruction", "expected"),
    [
        (1, None, "low"),
        (6, None, "medium"),
        (11, None, "high"),
        (0, "忘记全部记忆", "high"),
    ],
)
def test_preview_risk_rules(memory_count, instruction, expected):
    memory_ids = [f"mem_{index}" for index in range(memory_count)]
    plan = _preview(
        _service(),
        memory_ids=memory_ids,
        instruction=instruction,
    )

    assert plan.risk_level == expected
    assert all(item.risk_level == expected for item in plan.candidates)


def test_token_is_bound_to_user_plan_and_previewed_selection():
    service = _service()
    plan = _preview(service, memory_ids=["mem_1", "mem_2"])

    with pytest.raises(ConfirmationInvalidError):
        service.execute(_execute_request(plan, token="confirm_wrong"))
    with pytest.raises(ForgetAuthorizationError):
        service.execute(_execute_request(plan, user_id="usr_other"))
    with pytest.raises(ConfirmationInvalidError):
        service.execute(_execute_request(plan, plan_id="plan_other"))
    with pytest.raises(ForgetSelectionError):
        service.execute(
            _execute_request(plan, selected_ids=["mem_1", "mem_not_previewed"])
        )


def test_expired_token_is_rejected_at_the_exact_ttl_boundary():
    clock = MutableClock()
    service = _service(clock=clock)
    plan = _preview(service, memory_ids=["mem_1"])
    clock.advance(300)

    with pytest.raises(ConfirmationExpiredError):
        service.execute(_execute_request(plan))


def test_same_execution_request_is_idempotently_retried():
    service = _service()
    plan = _preview(service, memory_ids=["mem_1", "mem_2"])
    request = _execute_request(
        plan,
        request_id="req_stable",
        selected_ids=["mem_2", "mem_1"],
    )

    first = service.execute(request)
    replay = service.execute(request)

    assert replay == first
    with pytest.raises(ConfirmationInvalidError):
        service.execute(
            _execute_request(
                plan,
                request_id="req_different",
                selected_ids=["mem_2", "mem_1"],
            )
        )
    with pytest.raises(ConfirmationInvalidError):
        service.execute(
            _execute_request(
                plan,
                request_id="req_stable",
                selected_ids=["mem_1"],
            )
        )


def test_preview_and_execute_do_not_mutate_database_vector_or_audit(
    monkeypatch,
):
    from app.dependencies.mock_services import (
        MockAuditRepository,
        MockMemoryRepository,
        MockVectorStoreAdapter,
    )
    from repositories.sqlite import SQLiteAuditRepository, SQLiteMemoryRepository

    side_effects = []

    def forbidden(*_args, **_kwargs):
        side_effects.append("mutation")
        raise AssertionError("ForgetService must only return a deletion plan")

    monkeypatch.setattr(MockMemoryRepository, "logical_delete", forbidden)
    monkeypatch.setattr(MockVectorStoreAdapter, "delete", forbidden)
    monkeypatch.setattr(MockAuditRepository, "record", forbidden)
    monkeypatch.setattr(SQLiteMemoryRepository, "logical_delete", forbidden)
    monkeypatch.setattr(SQLiteAuditRepository, "record", forbidden)

    service = _service()
    plan = _preview(service, memory_ids=["mem_1"])
    execution = service.execute(_execute_request(plan))

    assert isinstance(execution, ForgetExecutionPlan)
    assert side_effects == []
