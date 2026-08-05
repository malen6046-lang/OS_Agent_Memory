"""Rule-based preference extraction adapted to the frozen V1.2.2 contract."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from threading import RLock
from typing import Any

from contracts.schemas.common import (
    MemoryStatus,
    PreferencePolarity,
    PreferenceScope,
)
from contracts.schemas.envelope import Envelope
from contracts.schemas.preference import PreferenceCandidate, PreferenceRecord

from .rules import RULES, PreferenceRule


_CJK_WHITESPACE = re.compile(
    r"(?<=[\u3400-\u4dbf\u4e00-\u9fff])\s+"
    r"(?=[\u3400-\u4dbf\u4e00-\u9fff])"
)
_GLOBAL_SCOPE_VALUE = "global"


class PreferenceService:
    """Process-local preference state backed by the Algorithm V1.1 rules.

    Persistence is intentionally not hidden in this service.  The current
    orchestration contract calls ``upsert`` before a memory row exists, so a
    database-backed preference unit of work must be introduced separately.
    """

    def __init__(
        self,
        rules: Iterable[PreferenceRule] = RULES,
    ) -> None:
        self._rules = tuple(rules)
        self._current: dict[
            tuple[str, str, str, str], PreferenceRecord
        ] = {}
        self._history: dict[tuple[str, str], list[PreferenceRecord]] = {}
        self._lock = RLock()

    def extract(
        self,
        events: list[Envelope],
    ) -> list[PreferenceCandidate]:
        """Extract deterministic candidates without changing service state."""
        candidates: list[PreferenceCandidate] = []
        for raw_event in events:
            event = Envelope.model_validate(raw_event)
            text = _event_text(event)
            normalized = _normalize_text(text).casefold()
            if not normalized:
                continue

            for rule, match_start in _select_rules(self._rules, normalized):
                keyword, key, value, category, confidence = rule
                candidates.append(
                    PreferenceCandidate(
                        user_id=event.user_id,
                        preference_key=key,
                        value=value,
                        category=category,
                        scope=PreferenceScope.GLOBAL,
                        scope_value=_GLOBAL_SCOPE_VALUE,
                        polarity=_polarity_at(normalized, match_start),
                        confidence=confidence,
                        evidence=[
                            {
                                "source_event_id": event.source_event_id,
                                "weight": confidence,
                            }
                        ],
                    )
                )
        return candidates

    def upsert(
        self,
        candidates: list[PreferenceCandidate],
    ) -> list[PreferenceRecord]:
        """Merge candidates atomically and retain immutable revision history."""
        validated_candidates = [
            PreferenceCandidate.model_validate(candidate)
            for candidate in candidates
        ]
        records: list[PreferenceRecord] = []
        with self._lock:
            working_current = dict(self._current)
            working_history = {
                key: list(history)
                for key, history in self._history.items()
            }
            for candidate in validated_candidates:
                state_key = (
                    candidate.user_id,
                    candidate.preference_key,
                    candidate.scope.value,
                    candidate.scope_value,
                )
                current = working_current.get(state_key)
                if current is None:
                    record = _new_record(candidate)
                else:
                    record = _merge_record(current, candidate)
                if current is None or record != current:
                    snapshot = record.model_copy(deep=True)
                    working_current[state_key] = snapshot
                    working_history.setdefault(
                        (candidate.user_id, record.preference_key),
                        [],
                    ).append(snapshot.model_copy(deep=True))
                records.append(record.model_copy(deep=True))
            self._current = working_current
            self._history = working_history
        return records

    def resolve(
        self,
        user_id: str,
        scene: str,
        keys: list[str] | None = None,
    ) -> list[PreferenceRecord]:
        """Resolve one active value per key with exact scope over global."""
        requested_keys = set(keys) if keys is not None else None
        selected: dict[str, tuple[tuple[int, int, float], PreferenceRecord]] = {}
        with self._lock:
            for (owner, key, scope, scope_value), record in self._current.items():
                if owner != user_id or record.status != MemoryStatus.ACTIVE:
                    continue
                if requested_keys is not None and key not in requested_keys:
                    continue
                exact_scope = scope != PreferenceScope.GLOBAL.value
                if exact_scope and scope_value != scene:
                    continue
                rank = (
                    1 if exact_scope else 0,
                    record.revision,
                    record.confidence,
                )
                previous = selected.get(key)
                if previous is None or rank > previous[0]:
                    selected[key] = (rank, record)

            return [
                selected[key][1].model_copy(deep=True)
                for key in sorted(selected)
            ]

    def history(
        self,
        user_id: str,
        preference_key: str,
    ) -> list[PreferenceRecord]:
        """Return isolated snapshots in insertion/revision order."""
        with self._lock:
            return [
                record.model_copy(deep=True)
                for record in self._history.get(
                    (user_id, preference_key),
                    [],
                )
            ]

def _new_record(candidate: PreferenceCandidate) -> PreferenceRecord:
    evidence = [dict(item) for item in candidate.evidence]
    return PreferenceRecord(
        preference_key=candidate.preference_key,
        value=candidate.value,
        category=candidate.category,
        scope=candidate.scope,
        scope_value=candidate.scope_value,
        polarity=candidate.polarity,
        confidence=candidate.confidence,
        evidence_count=len(evidence),
        evidence=evidence,
        revision=1,
        status=MemoryStatus.ACTIVE,
    )


def _merge_record(
    current: PreferenceRecord,
    candidate: PreferenceCandidate,
) -> PreferenceRecord:
    evidence = _merge_evidence(current.evidence, candidate.evidence)
    confidence = (
        max(current.confidence, candidate.confidence)
        if current.value == candidate.value
        else candidate.confidence
    )
    changed = (
        current.value != candidate.value
        or current.category != candidate.category
        or current.polarity != candidate.polarity
        or confidence != current.confidence
        or evidence != current.evidence
    )
    if not changed:
        return current

    return PreferenceRecord(
        preference_key=current.preference_key,
        value=candidate.value,
        category=candidate.category,
        scope=current.scope,
        scope_value=current.scope_value,
        polarity=candidate.polarity,
        confidence=confidence,
        evidence_count=len(evidence),
        evidence=evidence,
        revision=current.revision + 1,
        status=MemoryStatus.ACTIVE,
    )


def _merge_evidence(
    current: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = [dict(item) for item in current]
    seen = {_evidence_key(item) for item in merged}
    for item in incoming:
        plain = dict(item)
        key = _evidence_key(plain)
        if key not in seen:
            merged.append(plain)
            seen.add(key)
    return merged


def _evidence_key(item: dict[str, Any]) -> str:
    return json.dumps(
        item,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _event_text(event: Envelope) -> str:
    return "\n".join(_string_values(event.payload))


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


def _normalize_text(text: str) -> str:
    """Remove whitespace only when it separates two CJK characters."""
    previous = None
    normalized = text
    while normalized != previous:
        previous = normalized
        normalized = _CJK_WHITESPACE.sub("", normalized)
    return normalized


def _rule_match_spans(
    keyword: str,
    normalized_text: str,
) -> list[tuple[int, int]]:
    normalized_keyword = _normalize_text(keyword).casefold()
    if not normalized_keyword:
        return []
    start_boundary = (
        r"(?<![a-z0-9_])"
        if normalized_keyword[0].isascii()
        and normalized_keyword[0].isalnum()
        else ""
    )
    end_boundary = (
        r"(?![a-z0-9_])"
        if normalized_keyword[-1].isascii()
        and normalized_keyword[-1].isalnum()
        else ""
    )
    pattern = re.compile(
        start_boundary + re.escape(normalized_keyword) + end_boundary
    )
    return [match.span() for match in pattern.finditer(normalized_text)]


def _select_rules(
    rules: tuple[PreferenceRule, ...],
    normalized_text: str,
) -> list[tuple[PreferenceRule, int]]:
    matched: list[
        tuple[int, PreferenceRule, list[tuple[int, int]]]
    ] = []
    for index, rule in enumerate(rules):
        spans = _rule_match_spans(rule[0], normalized_text)
        if spans:
            matched.append((index, rule, spans))

    matched.sort(
        key=lambda item: (-len(_normalize_text(item[1][0])), item[0])
    )
    occupied: dict[tuple[str, str], list[tuple[int, int]]] = {}
    by_value: dict[
        tuple[str, str, str], tuple[int, PreferenceRule, int]
    ] = {}
    for index, rule, spans in matched:
        _, key, value, category, confidence = rule
        key_group = (key, category)
        effective_spans = [
            span
            for span in spans
            if not any(
                _contains(existing, span)
                for existing in occupied.get(key_group, [])
            )
        ]
        if not effective_spans:
            continue
        occupied.setdefault(key_group, []).extend(effective_spans)
        match_start = max(start for start, _ in effective_spans)
        value_key = (key, value, category)
        previous = by_value.get(value_key)
        if previous is None or (match_start, confidence) > (
            previous[2],
            previous[1][4],
        ):
            by_value[value_key] = (index, rule, match_start)

    by_key: dict[tuple[str, str], tuple[int, PreferenceRule, int]] = {}
    for item in by_value.values():
        index, rule, match_start = item
        key_group = (rule[1], rule[3])
        previous = by_key.get(key_group)
        if previous is None or (
            match_start,
            len(_normalize_text(rule[0])),
            rule[4],
        ) > (
            previous[2],
            len(_normalize_text(previous[1][0])),
            previous[1][4],
        ):
            by_key[key_group] = (index, rule, match_start)

    selected = sorted(
        by_key.values(),
        key=lambda item: (item[2], item[0]),
    )
    return [(rule, match_start) for _, rule, match_start in selected]


def _polarity_at(
    normalized_text: str,
    match_start: int,
) -> PreferencePolarity:
    prefix = normalized_text[max(0, match_start - 24) : match_start]
    chinese_context = prefix[-8:]
    if any(
        marker in chinese_context
        for marker in (
            "不要",
            "不想",
            "不喜欢",
            "不使用",
            "不用",
            "别用",
            "拒绝",
            "禁止",
            "关闭",
            "取消",
            "停止",
            "无需",
        )
    ):
        return PreferencePolarity.NEGATIVE
    if re.search(
        r"(?:do\s+not|don't|never|avoid|without|disable|not)"
        r"(?:\s+[a-z0-9_+-]+){0,3}\s*$",
        prefix,
    ):
        return PreferencePolarity.NEGATIVE
    return PreferencePolarity.POSITIVE


def _contains(
    outer: tuple[int, int],
    inner: tuple[int, int],
) -> bool:
    return outer[0] <= inner[0] and inner[1] <= outer[1]
