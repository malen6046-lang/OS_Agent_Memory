"""ConflictClassifier — 六分类冲突检测器。"""
from __future__ import annotations
from typing import Any


class ConflictClassifier:
    SIMILARITY_THRESHOLD = 0.85

    def classify(self, new_text: str, new_meta: dict, similar_entries: list[dict]) -> dict:
        if not similar_entries:
            return self._no_conflict()
        similar_entries = sorted(similar_entries, key=lambda x: x["score"], reverse=True)
        best = similar_entries[0]
        best_text = best["meta"].get("content_text", best["meta"].get("text", ""))
        best_meta = best["meta"]
        if new_text == best_text:
            return self._result("duplicate", best_meta.get("memory_id", ""), 0.95,
                                "keep_old", ["same_text"], False)
        score = best["score"]
        if score < self.SIMILARITY_THRESHOLD:
            return self._no_conflict()
        old_id = best_meta.get("memory_id", "")
        old_version = best_meta.get("revision", 1)
        if self._is_contradictory(best_text, new_text, best_meta, new_meta):
            return self._result("contradict", old_id, score, "manual_review",
                                ["same_entity", "contradictory_values"], True, old_version + 1)
        if self._is_superseding(best_meta, new_meta):
            return self._result("replace", old_id, score, "keep_new",
                                ["same_entity", "newer_effective_at"], True, old_version + 1)
        if self._is_complementary(best_text, new_text):
            return self._result("extend", old_id, score, "merge",
                                ["same_entity", "complementary"], True, old_version + 1)
        return self._result("support", old_id, score, "merge",
                            ["same_entity", "mutual_support"], True, old_version + 1)

    def _no_conflict(self) -> dict:
        return {"relation": "unrelated", "old_memory_id": None, "confidence": 0.0,
                "strategy": "keep_new", "reasons": ["new_entity"], "conflict": False,
                "new_version": 1}

    def _result(self, relation: str, old_id: str | None, confidence: float,
                strategy: str, reasons: list[str], conflict: bool,
                new_version: int = 1) -> dict:
        return {"relation": relation, "old_memory_id": old_id, "confidence": confidence,
                "strategy": strategy, "reasons": reasons, "conflict": conflict,
                "new_version": new_version}

    def _is_contradictory(self, t1: str, t2: str, m1: dict, m2: dict) -> bool:
        negations = ["不", "已废弃", "已更新为", "不可", "否", "非", "取消"]
        for neg in negations:
            if (neg in t1) != (neg in t2):
                return True
        c1, c2 = m1.get("content", {}), m2.get("content", {})
        if isinstance(c1, dict) and isinstance(c2, dict) and c1 and c2:
            for k in set(c1.keys()) & set(c2.keys()):
                if c1[k] != c2[k]:
                    return True
        return False

    def _is_superseding(self, old_meta: dict, new_meta: dict) -> bool:
        old_ts = old_meta.get("valid_from", old_meta.get("timestamp", 0))
        new_ts = new_meta.get("valid_from", new_meta.get("timestamp", 0))
        if old_ts and new_ts:
            return new_ts > old_ts
        src_priority = {"manual_config": 4, "tool_result": 3, "user_behavior": 2, "cross_scene": 1}
        return src_priority.get(new_meta.get("source_name", ""), 0) > src_priority.get(old_meta.get("source_name", ""), 0)

    def _is_complementary(self, t1: str, t2: str) -> bool:
        t1_set, t2_set = set(t1), set(t2)
        if not t1_set or not t2_set:
            return False
        overlap = len(t1_set & t2_set) / min(len(t1_set), len(t2_set))
        new_info = len(t2_set - t1_set) / max(len(t2_set), 1)
        return overlap > 0.3 and new_info > 0.2
