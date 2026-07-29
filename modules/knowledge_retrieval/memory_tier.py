"""MemoryTier — 三层记忆流转系统。

Based on C++ dsco/memory_tier:
  - Working  (short):  60s half-life, exponential decay
  - Episodic (medium): 3600s half-life
  - Semantic (long):   no decay, persistent

Promotion: access_count >= 3 AND importance >= 0.5
Decay: strength = exp(-ln(2) * age / half_life)
Eviction: strength < threshold → deactivated
Pinned: never decays, only explicit change allowed
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import IntEnum


class MemoryTier(IntEnum):
    WORKING = 0    # short-term
    EPISODIC = 1   # medium-term
    SEMANTIC = 2   # long-term


HALF_LIVES = {
    MemoryTier.WORKING: 60.0,
    MemoryTier.EPISODIC: 3600.0,
    MemoryTier.SEMANTIC: 0.0,  # no decay
}


@dataclass
class MemoryEntry:
    memory_id: str
    tier: MemoryTier
    value: str
    importance: float = 0.5
    strength: float = 1.0
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 1
    pinned: bool = False
    active: bool = True


class MemoryTierStore:
    """Manages three-tier memory with decay, consolidation, and eviction."""

    MAX_ENTRIES = 512

    def __init__(self):
        self._entries: dict[str, MemoryEntry] = {}
        self._tier_counts: dict[MemoryTier, int] = {t: 0 for t in MemoryTier}
        self.total_stores = 0
        self.total_promotions = 0
        self.total_evictions = 0

    # ── CRUD ──────────────────────────────────────────────────

    def put(self, memory_id: str, value: str, tier: MemoryTier = MemoryTier.WORKING,
            importance: float = 0.3) -> str:
        if len(self._entries) >= self.MAX_ENTRIES:
            self._evict_lowest()

        entry = MemoryEntry(
            memory_id=memory_id,
            tier=tier,
            value=value,
            importance=importance,
        )
        self._entries[memory_id] = entry
        self._tier_counts[tier] += 1
        self.total_stores += 1
        return memory_id

    def get(self, memory_id: str) -> MemoryEntry | None:
        entry = self._entries.get(memory_id)
        if entry and entry.active:
            entry.last_accessed = time.time()
            entry.access_count += 1
            return entry
        return None

    def pin(self, memory_id: str) -> None:
        entry = self._entries.get(memory_id)
        if entry:
            entry.pinned = True

    def unpin(self, memory_id: str) -> None:
        entry = self._entries.get(memory_id)
        if entry:
            entry.pinned = False

    def remove(self, memory_id: str) -> bool:
        entry = self._entries.get(memory_id)
        if entry and entry.active:
            entry.active = False
            self._tier_counts[entry.tier] -= 1
            return True
        return False

    # ── decay ─────────────────────────────────────────────────

    def decay_tick(self, threshold: float = 0.05) -> int:
        now = time.time()
        evicted = 0
        for entry in self._entries.values():
            if not entry.active or entry.pinned:
                continue
            entry.strength = self._calc_strength(entry, now)
            if entry.strength < threshold:
                self._tier_counts[entry.tier] -= 1
                entry.active = False
                self.total_evictions += 1
                evicted += 1
        return evicted

    @staticmethod
    def _calc_strength(entry: MemoryEntry, now: float) -> float:
        hl = HALF_LIVES.get(entry.tier, 0.0)
        if hl <= 0.0:
            return 1.0  # Semantic: no decay
        age = now - entry.created_at
        if age <= 0.0:
            return 1.0
        return math.exp(-0.693147 * age / hl)

    # ── consolidate ───────────────────────────────────────────

    def consolidate(self) -> int:
        """Promote entries that meet criteria to the next tier."""
        now = time.time()
        promotions = 0
        for entry in self._entries.values():
            if not entry.active or entry.tier >= MemoryTier.SEMANTIC:
                continue
            if entry.access_count >= 3 and entry.importance >= 0.5:
                old_tier = entry.tier
                entry.tier = MemoryTier(int(entry.tier) + 1)
                self._tier_counts[old_tier] -= 1
                self._tier_counts[entry.tier] += 1
                entry.created_at = now
                entry.strength = 1.0
                self.total_promotions += 1
                promotions += 1
        return promotions

    # ── tick ──────────────────────────────────────────────────

    def tick(self) -> int:
        return self.decay_tick(0.05) + self.consolidate()

    # ── counts ────────────────────────────────────────────────

    def tier_count(self, tier: MemoryTier | int) -> int:
        if isinstance(tier, int):
            tier = MemoryTier(tier)
        return self._tier_counts.get(tier, 0)

    def active_count(self) -> int:
        return sum(1 for e in self._entries.values() if e.active)

    # ── internal ──────────────────────────────────────────────

    def _evict_lowest(self) -> None:
        """Remove the lowest-strength non-pinned active entry."""
        weakest = None
        lowest_strength = float("inf")
        for eid, entry in self._entries.items():
            if entry.active and not entry.pinned and entry.strength < lowest_strength:
                lowest_strength = entry.strength
                weakest = eid
        if weakest:
            self.remove(weakest)
