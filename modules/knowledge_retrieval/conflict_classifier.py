"""ConflictClassifier — 六分类冲突检测器。

V1.1 conflict relations: duplicate | support | extend | replace | contradict | unrelated

Based on C++ OSMemory::rememberWithResolve() with enhancements:
  - Six-way classification instead of binary conflicted/not
  - Source reliability weighting from V1.1 priority rules
  - Version chain tracking (replaces, oldText)
"""
from __future__ import annotations

from typing import Any


class ConflictClassifier:
    """Detect and classify knowledge conflicts into 6 relation types."""

    SIMILARITY_THRESHOLD = 0.85

    def classify(
        self,
        new_text: str,
        new_meta: dict,
        similar_entries: list[dict],
    ) -> dict:
        """Classify new knowledge against similar existing entries.

        Returns:
          {"relation": str, "confidence": float, "strategy": str,
           "old_memory_id": str|None, "reasons": list[str], "conflict": bool}
        """
        if not similar_entries:
            return self._no_conflict()

        # Sort by score descending
        similar_entries = sorted(similar_entries, key=lambda x: x["score"], reverse=True)
        best = similar_entries[0]
        best_text = best["meta"].get("content_text", best["meta"].get("text", ""))
        best_meta = best["meta"]

        # 1. Exact duplicate
        if new_text == best_text:
            return self._result(
                "duplicate", best_meta.get("memory_id", ""), 0.95,
                "keep_old", ["same_text"], False,
            )

        score = best["score"]

        # 2. Below threshold → unrelated
        if score < self.SIMILARITY_THRESHOLD:
            return self._no_conflict()

        # 3. High similarity, different text → potential conflict
        old_id = best_meta.get("memory_id", "")
        old_version = best_meta.get("revision", 1)

        # Check for contradictory values
        if self._is_contradictory(best_text, new_text, best_meta, new_meta):
            return self._result(
                "contradict", old_id, score,
                "manual_review", ["same_entity", "contradictory_values"],
                True, old_version + 1,
            )

        # Same entity, newer effective date → replace
        if self._is_superseding(best_meta, new_meta):
            return self._result(
                "replace", old_id, score,
                "keep_new", ["same_entity", "newer_effective_at"],
                True, old_version + 1,
            )

        # Complementary info → extend
        if self._is_complementary(best_text, new_text):
            return self._result(
                "extend", old_id, score,
                "merge", ["same_entity", "complementary"],
                True, old_version + 1,
            )

        # Same topic, mutually reinforcing → support
        return self._result(
            "support", old_id, score,
            "merge", ["same_entity", "mutual_support"],
            True, old_version + 1,
        )

    # ── helpers ───────────────────────────────────────────────

    def _no_conflict(self) -> dict:
        return {
            "relation": "unrelated", "old_memory_id": None,
            "confidence": 0.0, "strategy": "keep_new",
            "reasons": ["new_entity"], "conflict": False,
            "new_version": 1,
        }

    def _result(
        self, relation: str, old_id: str | None, confidence: float,
        strategy: str, reasons: list[str], conflict: bool,
        new_version: int = 1,
    ) -> dict:
        return {
            "relation": relation,
            "old_memory_id": old_id,
            "confidence": confidence,
            "strategy": strategy,
            "reasons": reasons,
            "conflict": conflict,
            "new_version": new_version,
        }

    def _is_contradictory(self, t1: str, t2: str, m1: dict, m2: dict) -> bool:
        # Check for negations or opposite values
        negations = ["不", "已废弃", "已更新为", "不可", "否", "非", "取消"]
        for neg in negations:
            if (neg in t1 and neg not in t2) or (neg in t2 and neg not in t1):
                return True
        # Different values for same key in structured content
        c1 = m1.get("content", {})
        c2 = m2.get("content", {})
        if isinstance(c1, dict) and isinstance(c2, dict) and c1 and c2:
            common_keys = set(c1.keys()) & set(c2.keys())
            for k in common_keys:
                if c1[k] != c2[k]:
                    return True
        return False

    def _is_superseding(self, old_meta: dict, new_meta: dict) -> bool:
        old_ts = old_meta.get("valid_from", old_meta.get("timestamp", 0))
        new_ts = new_meta.get("valid_from", new_meta.get("timestamp", 0))
        if old_ts and new_ts:
            if isinstance(old_ts, str):
                return new_ts > old_ts
            return new_ts > old_ts
        # Higher source reliability wins
        source_priority = {"manual_config": 4, "tool_result": 3, "user_behavior": 2, "cross_scene": 1}
        old_src = old_meta.get("source_name", "cross_scene")
        new_src = new_meta.get("source_name", "cross_scene")
        return source_priority.get(new_src, 0) > source_priority.get(old_src, 0)

    def _is_complementary(self, t1: str, t2: str) -> bool:
        # Complementary if they share keywords but the new text adds new info
        t1_set = set(t1)
        t2_set = set(t2)
        if not t1_set or not t2_set:
            return False
        overlap = len(t1_set & t2_set) / min(len(t1_set), len(t2_set))
        new_info_ratio = len(t2_set - t1_set) / max(len(t2_set), 1)
        return overlap > 0.3 and new_info_ratio > 0.2
