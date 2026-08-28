"""Deterministic working-to-episodic-to-semantic memory flow for V1.2."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from threading import RLock


class MemoryFlowTier(StrEnum):
    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"


@dataclass(frozen=True)
class MemoryFlowState:
    memory_id: str
    user_id: str
    tier: MemoryFlowTier
    importance: float
    evidence_count: int
    access_count: int
    pinned: bool
    active: bool
    created_at: datetime
    last_accessed_at: datetime


class MemoryFlowController:
    """Track tier transitions without performing persistence side effects."""

    def __init__(self) -> None:
        self._states: dict[str, MemoryFlowState] = {}
        self._lock = RLock()

    def register(
        self,
        memory_id: str,
        user_id: str,
        *,
        importance: float,
        evidence_count: int = 1,
        pinned: bool = False,
        initial_tier: MemoryFlowTier | str | None = None,
        now: datetime | None = None,
    ) -> MemoryFlowState:
        owner = user_id.strip()
        identity = memory_id.strip()
        if not owner or not identity:
            raise ValueError("memory flow requires memory_id and user_id")
        importance = max(0.0, min(1.0, float(importance)))
        evidence_count = max(1, int(evidence_count))
        observed_at = _aware_utc(now)
        with self._lock:
            existing = self._states.get(identity)
            if existing is not None:
                if existing.user_id != owner:
                    raise ValueError("memory flow identity belongs to another user")
                updated = replace(
                    existing,
                    importance=max(existing.importance, importance),
                    evidence_count=max(existing.evidence_count, evidence_count),
                    pinned=existing.pinned or pinned,
                    active=True,
                )
                updated = self._promote(updated)
                self._states[identity] = updated
                return updated

            tier = (
                MemoryFlowTier(initial_tier)
                if initial_tier is not None
                else _initial_tier(importance, evidence_count, pinned)
            )
            state = MemoryFlowState(
                memory_id=identity,
                user_id=owner,
                tier=tier,
                importance=importance,
                evidence_count=evidence_count,
                access_count=0,
                pinned=pinned,
                active=True,
                created_at=observed_at,
                last_accessed_at=observed_at,
            )
            self._states[identity] = state
            return state

    def observe_access(
        self,
        memory_id: str,
        user_id: str,
        *,
        now: datetime | None = None,
    ) -> MemoryFlowState | None:
        observed_at = _aware_utc(now)
        with self._lock:
            state = self._states.get(memory_id)
            if state is None or not state.active or state.user_id != user_id:
                return None
            updated = replace(
                state,
                access_count=state.access_count + 1,
                last_accessed_at=observed_at,
            )
            updated = self._promote(updated)
            self._states[memory_id] = updated
            return updated

    def reinforce(
        self,
        memory_id: str,
        user_id: str,
        *,
        evidence_increment: int = 1,
    ) -> MemoryFlowState | None:
        with self._lock:
            state = self._states.get(memory_id)
            if state is None or not state.active or state.user_id != user_id:
                return None
            updated = replace(
                state,
                evidence_count=state.evidence_count
                + max(1, int(evidence_increment)),
            )
            updated = self._promote(updated)
            self._states[memory_id] = updated
            return updated

    def remove(self, memory_id: str) -> bool:
        with self._lock:
            state = self._states.get(memory_id)
            if state is None or not state.active:
                return False
            self._states[memory_id] = replace(state, active=False)
            return True

    def snapshot(
        self,
        memory_id: str,
        user_id: str,
    ) -> MemoryFlowState | None:
        with self._lock:
            state = self._states.get(memory_id)
            if state is None or state.user_id != user_id:
                return None
            return state

    @staticmethod
    def _promote(state: MemoryFlowState) -> MemoryFlowState:
        tier = state.tier
        if tier is MemoryFlowTier.WORKING and (
            state.access_count >= 3 or state.evidence_count >= 2
        ):
            tier = MemoryFlowTier.EPISODIC
        if tier is MemoryFlowTier.EPISODIC and (
            state.pinned
            or state.evidence_count >= 3
            or (state.importance >= 0.65 and state.access_count >= 6)
        ):
            tier = MemoryFlowTier.SEMANTIC
        return replace(state, tier=tier) if tier is not state.tier else state


def _initial_tier(
    importance: float,
    evidence_count: int,
    pinned: bool,
) -> MemoryFlowTier:
    if pinned:
        return MemoryFlowTier.SEMANTIC
    if evidence_count >= 2 or importance >= 0.75:
        return MemoryFlowTier.EPISODIC
    return MemoryFlowTier.WORKING


def _aware_utc(value: datetime | None) -> datetime:
    observed = value or datetime.now(timezone.utc)
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("memory flow clock must be timezone-aware")
    return observed.astimezone(timezone.utc)
