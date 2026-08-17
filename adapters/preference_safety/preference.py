"""Frozen PreferenceService Protocol over the unmodified V1.1 service."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from threading import RLock
from typing import Any

from contracts.schemas.common import (
    MemoryStatus,
    PreferencePolarity,
    PreferenceScope,
)
from contracts.schemas.envelope import Envelope
from contracts.schemas.preference import PreferenceCandidate, PreferenceRecord
from modules.preference_safety.algorithm_v1_1.preference_service import (
    PreferenceService as LegacyPreferenceService,
)
from modules.preference_safety.preference_extractor_v1_2 import (
    enhance_candidates,
)

from ._common import envelope_payload_text


class PreferenceServiceAdapter:
    """Convert frozen models to and from the legacy dictionary surface."""

    def __init__(
        self,
        legacy_service: Any | None = None,
        *,
        legacy_factory: Callable[[], Any] = LegacyPreferenceService,
    ) -> None:
        self._enhance_extraction = (
            legacy_service is None and legacy_factory is LegacyPreferenceService
        )
        self._extractor = legacy_service or legacy_factory()
        self._legacy_factory = (
            (lambda: legacy_service)
            if legacy_service is not None
            else legacy_factory
        )
        self._partitions: dict[tuple[str, str, str], Any] = {}
        self._lock = RLock()

    def extract(
        self,
        events: list[Envelope],
    ) -> list[PreferenceCandidate]:
        validated = [Envelope.model_validate(event) for event in events]
        raw_events = [
            {
                "text": envelope_payload_text(event.payload),
                "payload": dict(event.payload),
                "user_id": event.user_id,
                "scene": event.scene,
                "source_event_id": event.source_event_id,
                "request_id": event.request_id,
            }
            for event in validated
        ]
        with self._lock:
            raw_candidates = self._extractor.extract(raw_events)
        validated_raw = _raw_list(raw_candidates, "extract")
        if self._enhance_extraction:
            validated_raw = enhance_candidates(raw_events, validated_raw)
        return [
            _candidate_from_raw(raw_candidate)
            for raw_candidate in validated_raw
        ]

    def upsert(
        self,
        candidates: list[PreferenceCandidate],
    ) -> list[PreferenceRecord]:
        validated = [
            PreferenceCandidate.model_validate(candidate)
            for candidate in candidates
        ]
        grouped: dict[
            tuple[str, str, str],
            list[tuple[int, PreferenceCandidate]],
        ] = {}
        for index, candidate in enumerate(validated):
            grouped.setdefault(_partition_key(candidate), []).append(
                (index, candidate)
            )
        records: list[PreferenceRecord | None] = [None] * len(validated)
        with self._lock:
            for partition_key, indexed_candidates in grouped.items():
                legacy = self._partition(partition_key)
                raw_records = _raw_list(
                    legacy.upsert(
                        [
                            _candidate_to_raw(candidate)
                            for _, candidate in indexed_candidates
                        ]
                    ),
                    "upsert",
                )
                if len(raw_records) != len(indexed_candidates):
                    raise TypeError(
                        "legacy preference upsert returned the wrong count"
                    )
                for (index, _), raw_record in zip(
                    indexed_candidates,
                    raw_records,
                ):
                    records[index] = _record_from_raw(raw_record)
        if any(record is None for record in records):
            raise RuntimeError("preference adapter lost an upsert result")
        return [record for record in records if record is not None]

    def resolve(
        self,
        user_id: str,
        scene: str,
        keys: list[str] | None = None,
    ) -> list[PreferenceRecord]:
        selected: dict[str, tuple[int, PreferenceRecord]] = {}
        requested_keys = set(keys) if keys is not None else None
        with self._lock:
            for partition_key, legacy in self._partitions.items():
                owner, scope, scope_value = partition_key
                if owner != user_id:
                    continue
                if scope == PreferenceScope.TOOL.value:
                    continue
                if (
                    scope == PreferenceScope.SCENE.value
                    and scope_value != scene
                ):
                    continue
                priority = (
                    1 if scope == PreferenceScope.SCENE.value else 0
                )
                raw_records = _raw_list(
                    legacy.resolve(
                        user_id=user_id,
                        scene=scene,
                        keys=keys,
                    ),
                    "resolve",
                )
                for raw_record in raw_records:
                    raw_owner = raw_record.get("user_id")
                    if raw_owner is not None and raw_owner != user_id:
                        continue
                    record = _record_from_raw(raw_record)
                    if (
                        requested_keys is not None
                        and record.preference_key not in requested_keys
                    ):
                        continue
                    previous = selected.get(record.preference_key)
                    if previous is None or priority > previous[0]:
                        selected[record.preference_key] = (priority, record)
        return [selected[key][1] for key in sorted(selected)]

    def history(
        self,
        user_id: str,
        preference_key: str,
    ) -> list[PreferenceRecord]:
        records: list[PreferenceRecord] = []
        with self._lock:
            for partition_key, legacy in self._partitions.items():
                if partition_key[0] != user_id:
                    continue
                raw_records = _raw_list(
                    legacy.history(
                        user_id=user_id,
                        preference_key=preference_key,
                    ),
                    "history",
                )
                for raw_record in raw_records:
                    owner = raw_record.get("user_id")
                    if owner is not None and owner != user_id:
                        continue
                    record = _record_from_raw(raw_record)
                    if record.preference_key == preference_key:
                        records.append(record)
        return records

    def _partition(self, key: tuple[str, str, str]) -> Any:
        legacy = self._partitions.get(key)
        if legacy is None:
            legacy = self._legacy_factory()
            self._partitions[key] = legacy
        return legacy


def build_preference_service() -> PreferenceServiceAdapter:
    """Create the synchronous PreferenceService implementation for DI."""
    return PreferenceServiceAdapter()


def _candidate_from_raw(raw: Mapping[str, Any]) -> PreferenceCandidate:
    source_event_id = _non_empty(raw.get("source_event_id"))
    evidence = (
        [
            {
                "source_event_id": source_event_id,
                "weight": raw.get("confidence", 0.0),
            }
        ]
        if source_event_id is not None
        else []
    )
    scope = raw.get("scope", PreferenceScope.GLOBAL.value)
    scope_value = (
        "global"
        if scope == PreferenceScope.GLOBAL.value
        else (
            _non_empty(raw.get("scope_value"))
            or _non_empty(raw.get("scene"))
            or "global"
        )
    )
    return PreferenceCandidate(
        user_id=_required_string(raw, "user_id"),
        preference_key=_required_string(raw, "preference_key"),
        value=raw.get("value"),
        category=_required_string(raw, "category"),
        scope=scope,
        scope_value=scope_value,
        polarity=raw.get("polarity", PreferencePolarity.POSITIVE.value),
        confidence=raw.get("confidence"),
        evidence=evidence,
    )


def _candidate_to_raw(candidate: PreferenceCandidate) -> dict[str, Any]:
    source_event_id = _source_event_id(candidate.evidence)
    scope_value = (
        "global"
        if candidate.scope is PreferenceScope.GLOBAL
        else candidate.scope_value
    )
    return {
        "user_id": candidate.user_id,
        "preference_key": candidate.preference_key,
        "value": candidate.value,
        "category": candidate.category,
        "scope": candidate.scope.value,
        "scope_value": scope_value,
        "scene": scope_value,
        "polarity": candidate.polarity.value,
        "confidence": candidate.confidence,
        "source_event_id": source_event_id or "",
    }


def _partition_key(
    candidate: PreferenceCandidate,
) -> tuple[str, str, str]:
    scope_value = (
        "global"
        if candidate.scope is PreferenceScope.GLOBAL
        else candidate.scope_value
    )
    return (candidate.user_id, candidate.scope.value, scope_value)


def _record_from_raw(raw: Mapping[str, Any]) -> PreferenceRecord:
    evidence = _valid_evidence(raw.get("evidence", []))
    return PreferenceRecord(
        preference_key=_required_string(raw, "preference_key"),
        value=raw.get("value"),
        category=_required_string(raw, "category"),
        scope=raw.get("scope", "global"),
        scope_value=_non_empty(raw.get("scope_value")) or "global",
        polarity=raw.get("polarity", PreferencePolarity.POSITIVE.value),
        confidence=raw.get("confidence"),
        evidence_count=len(evidence),
        evidence=evidence,
        revision=raw.get("revision", 1),
        status=raw.get("status", MemoryStatus.ACTIVE.value),
    )


def _raw_list(value: Any, operation: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        raise TypeError(f"legacy preference {operation} must return a list")
    result: list[Mapping[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise TypeError(
                f"legacy preference {operation} items must be mappings"
            )
        result.append(item)
    return result


def _required_string(raw: Mapping[str, Any], key: str) -> str:
    value = _non_empty(raw.get(key))
    if value is None:
        raise TypeError(f"legacy preference result has no valid {key}")
    return value


def _non_empty(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _source_event_id(evidence: list[dict[str, Any]]) -> str | None:
    for item in evidence:
        value = _non_empty(item.get("source_event_id"))
        if value is not None:
            return value
    return None


def _valid_evidence(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    evidence: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        plain = dict(item)
        if any(
            key.endswith("_id") and _non_empty(field_value) is None
            for key, field_value in plain.items()
        ):
            continue
        evidence.append(plain)
    return evidence
