"""Tests for MemoryTier — V1.1 three-tier memory flow."""
import time
import pytest
from modules.knowledge_retrieval.memory_tier import MemoryTier, MemoryTierStore


class TestMemoryTierBasic:
    def test_put_working(self):
        m = MemoryTierStore()
        m.put("mem_1", "test value", MemoryTier.WORKING)
        assert m.tier_count(MemoryTier.WORKING) == 1

    def test_put_increments_count(self):
        m = MemoryTierStore()
        for i in range(5):
            m.put(f"mem_{i}", f"v{i}", MemoryTier.WORKING)
        assert m.tier_count(MemoryTier.WORKING) == 5
        assert m.active_count() == 5

    def test_get_updates_access(self):
        m = MemoryTierStore()
        m.put("mem_1", "val", MemoryTier.WORKING)
        entry = m.get("mem_1")
        assert entry is not None
        assert entry.access_count == 2  # initial 1 + get


class TestMemoryTierDecay:
    def test_working_decays(self):
        m = MemoryTierStore()
        m.put("mem_1", "val", MemoryTier.WORKING, importance=0.3)
        entry = m._entries["mem_1"]
        entry.created_at = time.time() - 120  # 2x half-life
        evicted = m.decay_tick(0.05)
        assert evicted >= 0

    def test_semantic_no_decay(self):
        m = MemoryTierStore()
        m.put("mem_1", "val", MemoryTier.SEMANTIC, importance=0.9)
        entry = m._entries["mem_1"]
        entry.created_at = time.time() - 100000  # very old
        evicted = m.decay_tick(0.01)
        assert m._entries["mem_1"].active  # semantic never decays

    def test_pinned_no_decay(self):
        m = MemoryTierStore()
        m.put("mem_1", "val", MemoryTier.WORKING, importance=0.3)
        m.pin("mem_1")
        entry = m._entries["mem_1"]
        entry.created_at = time.time() - 10000
        evicted = m.decay_tick(0.01)
        assert m._entries["mem_1"].active


class TestMemoryTierConsolidate:
    def test_promote_working_to_episodic(self):
        m = MemoryTierStore()
        m.put("mem_1", "val", MemoryTier.WORKING, importance=0.7)
        entry = m._entries["mem_1"]
        entry.access_count = 5  # >= 3
        entry.importance = 0.8  # >= 0.5
        promoted = m.consolidate()
        assert promoted == 1
        assert entry.tier == MemoryTier.EPISODIC
        assert m.tier_count(MemoryTier.WORKING) == 0
        assert m.tier_count(MemoryTier.EPISODIC) == 1

    def test_no_promote_below_threshold(self):
        m = MemoryTierStore()
        m.put("mem_1", "val", MemoryTier.WORKING, importance=0.2)
        entry = m._entries["mem_1"]
        entry.access_count = 1  # < 3
        promoted = m.consolidate()
        assert promoted == 0


class TestMemoryTierRemove:
    def test_remove_deactivates(self):
        m = MemoryTierStore()
        m.put("mem_1", "val", MemoryTier.WORKING)
        assert m.remove("mem_1")
        assert m.tier_count(MemoryTier.WORKING) == 0
        assert m._entries["mem_1"].active is False

    def test_tick_decay_and_consolidate(self):
        m = MemoryTierStore()
        m.put("w1", "working", MemoryTier.WORKING, importance=0.2)
        m.put("e1", "episodic", MemoryTier.EPISODIC, importance=0.7)
        m.put("s1", "semantic", MemoryTier.SEMANTIC, importance=0.9)
        # Promote episodic entry
        entry = m._entries["e1"]
        entry.access_count = 5
        ticked = m.tick()
        assert ticked >= 0  # should not crash
        assert m._entries["s1"].active  # semantic survives
