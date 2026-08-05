"""Private shape conversions shared by the legacy adapters."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any


def envelope_payload_text(payload: Mapping[str, Any]) -> str:
    """Select the legacy text input without exposing contract internals."""
    for key in ("text", "content_text", "content", "result", "body"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    strings = list(_string_values(payload))
    if strings:
        return "\n".join(strings)
    return json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def unique_strings(values: Iterable[Any]) -> list[str]:
    """Return non-empty strings once, preserving first-seen order."""
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        normalized = value.strip()
        if normalized and normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return result


def _string_values(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        if value.strip():
            yield value.strip()
    elif isinstance(value, Mapping):
        for child in value.values():
            yield from _string_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _string_values(child)
