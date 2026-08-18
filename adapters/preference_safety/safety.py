"""Frozen SafetyService Protocol over the unmodified V1.1 detector."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from contracts.schemas.envelope import Envelope
from contracts.schemas.safety import SafetyCheckResult
from modules.preference_safety.algorithm_v1_1.safety_service import (
    SafetyService as LegacySafetyService,
)

from ._common import envelope_payload_text, unique_strings


class SafetyServiceAdapter:
    """Map legacy entity findings to a non-sensitive frozen decision."""

    def __init__(self, legacy_service: Any | None = None) -> None:
        self._legacy = legacy_service or LegacySafetyService()

    def check(self, envelope: Envelope) -> SafetyCheckResult:
        event = Envelope.model_validate(envelope)
        raw = self._legacy.check(envelope_payload_text(event.payload))
        if not isinstance(raw, Mapping):
            raise TypeError("legacy safety check must return a mapping")

        entities = raw.get("entities", [])
        if not isinstance(entities, list):
            raise TypeError("legacy safety entities must be a list")
        entity_types = unique_strings(
            entity.get("type")
            for entity in entities
            if isinstance(entity, Mapping)
        )
        blocked = bool(raw.get("block")) or bool(raw.get("has_sensitive"))
        return SafetyCheckResult(
            allowed=not blocked,
            reason_codes=[_reason_code(item) for item in entity_types],
            entity_types=entity_types,
        )


def build_safety_service() -> SafetyServiceAdapter:
    """Create the synchronous SafetyService implementation for DI."""
    return SafetyServiceAdapter()


def _reason_code(entity_type: str) -> str:
    if entity_type == "sensitive_keyword":
        return "sensitive.keyword"
    return f"sensitive.{entity_type}"
