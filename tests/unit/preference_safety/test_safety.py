"""Acceptance tests for sensitive-content checks."""

from __future__ import annotations

import inspect
from datetime import datetime, timezone

import pytest

from contracts.schemas.envelope import Envelope
from contracts.schemas.safety import SafetyCheckResult
from modules.preference_safety import SafetyService


NOW = datetime(2099, 8, 5, 12, 0, tzinfo=timezone.utc)


def _envelope(payload: dict) -> Envelope:
    return Envelope(
        contract_version="1.0",
        request_id="req_safety",
        idempotency_key="idem_safety",
        user_id="usr_1",
        scene="desktop",
        source="tool_result",
        source_event_id="evt_safety",
        occurred_at=NOW,
        payload=payload,
    )


def test_check_keeps_the_frozen_synchronous_signature():
    assert not inspect.iscoroutinefunction(SafetyService.check)
    assert list(inspect.signature(SafetyService.check).parameters) == [
        "self",
        "envelope",
    ]


@pytest.mark.parametrize(
    ("text", "entity_type"),
    [
        ("联系电话 13812345678", "phone"),
        ("身份证 11010519491231002X", "id_card"),
        ("银行卡 6222021234567890123", "bank_card"),
        ("邮箱 alice@example.com", "email"),
        ("api_key=abcdefghijklmnopqrstuv", "api_key"),
        ("password: correct-horse-battery-staple", "password"),
        ("请记录家庭住址", "sensitive_keyword"),
    ],
)
def test_sensitive_rules_return_only_contract_categories(text, entity_type):
    result = SafetyService().check(
        _envelope({"nested": [{"content": text}]})
    )

    assert isinstance(result, SafetyCheckResult)
    assert result.allowed is False
    assert entity_type in result.entity_types
    assert len(result.entity_types) == len(set(result.entity_types))
    assert len(result.reason_codes) == len(set(result.reason_codes))
    assert set(type(result).model_fields) == {
        "allowed",
        "reason_codes",
        "entity_types",
    }


def test_safe_nested_payload_is_allowed_and_input_is_not_mutated():
    event = _envelope(
        {"steps": ["按 Ctrl+Alt+T 打开终端", {"result": "完成"}]}
    )
    before = event.model_dump(mode="json")

    result = SafetyService().check(event)

    assert result == SafetyCheckResult(allowed=True)
    assert event.model_dump(mode="json") == before


@pytest.mark.parametrize(
    ("payload", "entity_type"),
    [
        ({"password": "correct-horse"}, "password"),
        ({"credentials": {"api_key": "short-value"}}, "api_key"),
        ({"db_password": "correct-horse"}, "password"),
        ({"client_secret": "short-value"}, "api_key"),
        ({"refresh_token": "short-value"}, "api_key"),
        ({"private_key": "short-value"}, "api_key"),
        ({"登录密码": "correct-horse"}, "password"),
        ({"访问令牌": "short-value"}, "api_key"),
        ({"私钥": "short-value"}, "api_key"),
    ],
)
def test_sensitive_structured_field_names_are_detected(payload, entity_type):
    result = SafetyService().check(_envelope(payload))

    assert result.allowed is False
    assert entity_type in result.entity_types


@pytest.mark.parametrize(
    "payload",
    [
        {"token_count": 42},
        {"token_limit": 4096},
        {"api_key_length": 32},
    ],
)
def test_non_secret_token_metadata_fields_are_allowed(payload):
    assert SafetyService().check(_envelope(payload)).allowed is True


def test_id_card_span_is_not_reported_again_as_a_bank_card():
    result = SafetyService().check(
        _envelope({"text": "11010519491231002X"})
    )

    assert "id_card" in result.entity_types
    assert "bank_card" not in result.entity_types


def test_result_and_logs_never_expose_sensitive_values(caplog):
    secrets = [
        "13812345678",
        "alice@example.com",
        "api_key=abcdefghijklmnopqrstuv",
    ]
    event = _envelope({"content": "；".join(secrets)})

    result = SafetyService().check(event)
    serialized = result.model_dump_json()
    logs = caplog.text

    assert result.allowed is False
    for secret in secrets:
        assert secret not in serialized
        assert secret not in logs
