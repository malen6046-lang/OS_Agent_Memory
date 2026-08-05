"""PII and secret detection adapted to the frozen safety contract."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from contracts.schemas.envelope import Envelope
from contracts.schemas.safety import SafetyCheckResult


_DETECTORS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "phone",
        "sensitive.phone",
        re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    ),
    (
        "id_card",
        "sensitive.id_card",
        re.compile(
            r"(?<!\d)[1-9]\d{5}(?:18|19|20)\d{2}"
            r"(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])"
            r"\d{3}[\dXx](?!\d)"
        ),
    ),
    (
        "bank_card",
        "sensitive.bank_card",
        re.compile(r"(?<!\d)\d{16,19}(?!\d)"),
    ),
    (
        "email",
        "sensitive.email",
        re.compile(
            r"(?<![\w.+-])[A-Za-z0-9._%+-]+@"
            r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.-])"
        ),
    ),
    (
        "api_key",
        "sensitive.api_key",
        re.compile(
            r"(?:\bsk-[A-Za-z0-9_-]{16,}\b|"
            r"\b(?:sk|api[_-]?key|token|secret)\s*[:=]\s*"
            r"[A-Za-z0-9_.-]{16,})",
            re.IGNORECASE,
        ),
    ),
    (
        "password",
        "sensitive.password",
        re.compile(
            r"(?:password|passwd|pwd|密码|口令)\s*[:=：]\s*\S+",
            re.IGNORECASE,
        ),
    ),
)

_SENSITIVE_KEYWORDS = (
    "身份证",
    "银行卡",
    "社保号",
    "护照号",
    "军官证",
    "家庭住址",
    "身份证号",
    "手机号码",
    "银行卡号",
    "root密码",
    "admin密码",
    "administrator密码",
)


class SafetyService:
    """Detect sensitive content without returning or logging matched values."""

    def check(self, envelope: Envelope) -> SafetyCheckResult:
        event = Envelope.model_validate(envelope)
        text = "\n".join(_string_values(event.payload))
        entity_types, reason_codes = _sensitive_field_findings(event.payload)
        id_card_spans: list[tuple[int, int]] = []

        for entity_type, reason_code, pattern in _DETECTORS:
            matches = list(pattern.finditer(text))
            if entity_type == "bank_card" and id_card_spans:
                matches = [
                    match
                    for match in matches
                    if not any(
                        _overlaps(match.span(), id_card_span)
                        for id_card_span in id_card_spans
                    )
                ]
            if matches:
                entity_types.append(entity_type)
                reason_codes.append(reason_code)
                if entity_type == "id_card":
                    id_card_spans.extend(match.span() for match in matches)

        if any(keyword in text for keyword in _SENSITIVE_KEYWORDS):
            entity_types.append("sensitive_keyword")
            reason_codes.append("sensitive.keyword")

        return SafetyCheckResult(
            allowed=not entity_types,
            reason_codes=list(dict.fromkeys(reason_codes)),
            entity_types=list(dict.fromkeys(entity_types)),
        )

    def check_batch(
        self,
        envelopes: list[Envelope],
    ) -> list[SafetyCheckResult]:
        """Retain the donor batch convenience without changing the Protocol."""
        return [self.check(envelope) for envelope in envelopes]


def _string_values(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        if value.strip():
            yield value.strip()
    elif isinstance(value, dict):
        for child in value.values():
            yield from _string_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _string_values(child)


def _sensitive_field_findings(
    value: Any,
) -> tuple[list[str], list[str]]:
    entity_types: list[str] = []
    reason_codes: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            field_type = _sensitive_field_type(key)
            if field_type == "password":
                entity_types.append("password")
                reason_codes.append("sensitive.password")
            elif field_type == "api_key":
                entity_types.append("api_key")
                reason_codes.append("sensitive.api_key")
            child_types, child_reasons = _sensitive_field_findings(child)
            entity_types.extend(child_types)
            reason_codes.extend(child_reasons)
    elif isinstance(value, list):
        for child in value:
            child_types, child_reasons = _sensitive_field_findings(child)
            entity_types.extend(child_types)
            reason_codes.extend(child_reasons)
    return entity_types, reason_codes


def _sensitive_field_type(key: str) -> str | None:
    folded = key.casefold()
    if any(marker in key for marker in ("密码", "口令")):
        return "password"
    if any(marker in key for marker in ("令牌", "私钥", "密钥")):
        return "api_key"

    tokens = [token for token in re.split(r"[^a-z0-9]+", folded) if token]
    compact = "".join(tokens)
    metadata_suffixes = {
        "budget",
        "count",
        "expires",
        "expiry",
        "length",
        "limit",
        "name",
        "type",
        "usage",
    }
    if tokens and tokens[-1] in metadata_suffixes:
        return None
    if any(token in {"password", "passwd", "pwd"} for token in tokens):
        return "password"
    if compact.endswith(("password", "passwd", "pwd")):
        return "password"
    if any(token in {"secret", "token"} for token in tokens):
        return "api_key"
    if compact.endswith(
        (
            "apikey",
            "apisecret",
            "accesstoken",
            "refreshtoken",
            "clientsecret",
            "privatekey",
        )
    ):
        return "api_key"
    if len(tokens) >= 2 and tokens[-2:] == ["private", "key"]:
        return "api_key"
    return None


def _overlaps(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] < right[1] and right[0] < left[1]
