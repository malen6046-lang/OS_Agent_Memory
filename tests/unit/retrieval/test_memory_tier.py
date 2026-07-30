"""MemoryTier unit tests."""
import time
from modules.knowledge_retrieval.memory_tier import MemoryTier, MemoryTierStore, HALF_LIVES


class TestBasic:
    def test_put(self):
        m = MemoryTierStore(); m.put("m1","v",MemoryTier.WORKING)
        assert m.tier_count(MemoryTier.WORKING) == 1
    def test_get(self):
        m = MemoryTierStore(); m.put("m1","v",MemoryTier.WORKING)
        assert m.get("m1") is not None


class TestDecay:
    def test_semantic_never(self):
        m = MemoryTierStore(); m.put("m1","v",MemoryTier.SEMANTIC,0.9)
        e = m._entries["m1"]; e.created_at = time.time() - 100000
        m.decay_tick(0.01)
        assert m._entries["m1"].active
    def test_pinned_never(self):
        m = MemoryTierStore(); m.put("m1","v",MemoryTier.WORKING,0.3); m.pin("m1")
        e = m._entries["m1"]; e.created_at = time.time() - 10000
        m.decay_tick(0.01)
        assert m._entries["m1"].active


class TestConsolidate:
    def test_promote(self):
        m = MemoryTierStore(); m.put("m1","v",MemoryTier.WORKING,0.8)
        e = m._entries["m1"]; e.access_count = 5
        assert m.consolidate() == 1 and e.tier == MemoryTier.EPISODIC
    def test_no_promote(self):
        m = MemoryTierStore(); m.put("m1","v",MemoryTier.WORKING,0.2)
        e = m._entries["m1"]; e.access_count = 1
        assert m.consolidate() == 0


class TestRemove:
    def test_remove(self):
        m = MemoryTierStore(); m.put("m1","v",MemoryTier.WORKING)
        assert m.remove("m1") and m.tier_count(MemoryTier.WORKING) == 0
    def test_tick(self):
        m = MemoryTierStore()
        m.put("w","w",MemoryTier.WORKING,0.2)
        m.put("e","e",MemoryTier.EPISODIC,0.7)
        m.put("s","s",MemoryTier.SEMANTIC,0.9)
        e_entry = m._entries["e"]; e_entry.access_count = 5
        assert m.tick() >= 0
        assert m._entries["s"].active
