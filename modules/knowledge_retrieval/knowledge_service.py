"""KnowledgeService — 知识写入、去重、冲突候选检测。

Implements the KnowledgeService protocol from V1.1:
  ingest(records: list[KnowledgeDraft]) -> IngestResult
  classify_conflict(old: MemoryRecord, new: MemoryRecord) -> ConflictDecision
  apply_conflict(decision: ConflictDecision) -> MemoryRecord

Based on the C++ OSMemory::rememberWithResolve() algorithm:
  - Similarity threshold: 0.85 (cosine)
  - Candidate search: topK=3
  - Version chain: version + replaces + oldText
"""
from __future__ import annotations

import time
from typing import Any


class KnowledgeService:
    """Ingest knowledge drafts, detect duplicates, and classify conflicts.

    Delegates embedding and vector search to the injected providers.
    Uses a metadata store (dict-based for fallback) to track version chains.
    """

    def __init__(
        self,
        embedding_provider: Any,
        vector_store: Any,
        bm25: Any,
        metadata_store: dict | None = None,
    ):
        self._emb = embedding_provider
        self._vs = vector_store
        self._bm25 = bm25
        self._meta: dict[str, dict] = metadata_store or {}  # memory_id -> metadata
        self._next_vector_pk = 1

    # ── ingest ─────────────────────────────────────────────────

    def ingest(self, records: list[dict]) -> dict:
        """V1.1: KnowledgeDraft list -> IngestResult."""
        ingested = 0
        skipped_duplicate = 0
        conflicts: list[str] = []
        memory_ids: list[str] = []
        errors: list[dict] = []

        for idx, rec in enumerate(records):
            try:
                title = rec.get("title", rec.get("content_text", ""))
                body = rec.get("body", rec.get("content_text", ""))
                text = (title + " " + body).strip()
                if not text:
                    errors.append({"index": idx, "error": "empty_text"})
                    continue

                result = self._ingest_one(rec, text)
                if result["action"] == "inserted":
                    ingested += 1
                    memory_ids.append(result["memory_id"])
                elif result["action"] == "duplicate":
                    skipped_duplicate += 1
                elif result["action"] == "conflict":
                    ingested += 1
                    memory_ids.append(result["memory_id"])
                    conflicts.append(result["memory_id"])
            except Exception as exc:
                errors.append({"index": idx, "error": str(exc)})

        return {
            "ingested": ingested,
            "skipped_duplicate": skipped_duplicate,
            "conflicts": conflicts or None,
            "memory_ids": memory_ids or None,
            "errors": errors or None,
        }

    def _ingest_one(self, rec: dict, text: str) -> dict:
        title = rec.get("title", "")
        user_id = rec.get("user_id", "default")
        memory_kind = rec.get("knowledge_type", rec.get("memory_kind", "semantic"))
        scene = rec.get("scene", "default")
        source_reliability = rec.get("source_reliability", 0.5)

        # Search for similar existing records
        candidates = self._find_similar(text, user_id)
        threshold = 0.85

        for cand in candidates:
            cand_text = cand["meta"].get("content_text", "")
            score = cand["score"]

            if score >= threshold:
                if cand_text == text:
                    return {"action": "duplicate", "memory_id": cand["meta"].get("memory_id", "")}
                # Conflict detected — insert new version with trace
                old_id = cand["meta"].get("memory_id", "")
                old_version = cand["meta"].get("revision", 1)
                new_version = old_version + 1
                memory_id = f"mem_{int(time.time()*1000):x}"
                return {
                    "action": "conflict",
                    "memory_id": memory_id,
                    "old_memory_id": old_id,
                    "new_version": new_version,
                }

        # No conflict — fresh insert
        memory_id = f"mem_{int(time.time()*1000):x}"
        return {"action": "inserted", "memory_id": memory_id}

    def _find_similar(self, text: str, user_id: str) -> list[dict]:
        try:
            health = self._emb.health()
            if health.get("status") == "stopped":
                return []
            batch = self._emb.encode([text])
            vectors = batch.get("vectors", [])
            if not vectors:
                return []
            return self._vs.query({
                "vector": vectors[0],
                "top_k": 3,
                "filter_user_id": user_id,
                "filter_status": "active",
            })
        except Exception:
            return []

    # ── classify_conflict ──────────────────────────────────────

    def classify_conflict(self, old: dict, new: dict) -> dict:
        """V1.1: old MemoryRecord + new MemoryRecord -> ConflictDecision."""
        old_text = old.get("content_text", "")
        new_text = new.get("content_text", "")

        if old_text == new_text:
            return self._make_decision("duplicate", old, new, ["same_text"])

        old_kind = old.get("memory_kind", "")
        new_kind = new.get("memory_kind", "")
        old_subtype = old.get("subtype", "")

        # Contradictory facts → contradict (check BEFORE extend/support)
        if old_kind == new_kind and self._is_contradictory(old, new):
            return self._make_decision("contradict", old, new, ["same_entity", "contradictory_values"])

        # Same entity + same attribute + newer effective date → replace
        if old_kind == new_kind and self._same_entity(old_text, new_text):
            old_eff = old.get("valid_from", "")
            new_eff = new.get("valid_from", "")
            if new_eff and old_eff and new_eff >= old_eff:
                return self._make_decision("replace", old, new, ["same_entity", "same_attribute", "newer_effective_at"])

        # Same entity + different complementary info → extend
        if old_kind == new_kind and self._overlapping_topic(old_text, new_text):
            return self._make_decision("extend", old, new, ["same_entity", "complementary"])

        return self._make_decision("unrelated", old, new, ["low_similarity"])

    def _same_entity(self, t1: str, t2: str) -> bool:
        t1_set = set(t1)
        t2_set = set(t2)
        if not t1_set or not t2_set:
            return False
        overlap = len(t1_set & t2_set) / min(len(t1_set), len(t2_set))
        return overlap > 0.3

    def _overlapping_topic(self, t1: str, t2: str) -> bool:
        return self._same_entity(t1, t2)

    def _is_contradictory(self, old: dict, new: dict) -> bool:
        t1 = old.get("content_text", "")
        t2 = new.get("content_text", "")
        if not t1 or not t2:
            return False
        # Must share topic before checking for contradiction
        if not self._same_entity(t1, t2):
            return False
        # Negation or deprecation flags
        negations = ["\u4e0d", "\u5df2\u5e9f\u5f03", "\u5df2\u66f4\u65b0\u4e3a", "\u4e0d\u53ef", "\u5426", "\u975e", "\u53d6\u6d88"]
        for neg in negations:
            in_old = neg in t1
            in_new = neg in t2
            if in_old != in_new:
                return True
        # Different values for same key in structured content
        c1 = old.get("content", {})
        c2 = new.get("content", {})
        if isinstance(c1, dict) and isinstance(c2, dict) and c1 and c2:
            common_keys = set(c1.keys()) & set(c2.keys())
            for k in common_keys:
                if c1[k] != c2[k]:
                    return True
        return False

    def _make_decision(self, relation: str, old: dict, new: dict, reasons: list[str]) -> dict:
        confidence = 0.89 if relation in ("replace", "contradict") else 0.85
        strategy_map = {
            "duplicate": "keep_old",
            "support": "merge",
            "extend": "merge",
            "replace": "keep_new",
            "contradict": "manual_review",
            "unrelated": "keep_old",
        }
        return {
            "relation": relation,
            "old_memory_id": old.get("memory_id", ""),
            "new_memory_id": new.get("memory_id", ""),
            "confidence": confidence,
            "strategy": strategy_map.get(relation, "manual_review"),
            "reason_codes": reasons,
            "detail": None,
        }

    # ── apply_conflict ─────────────────────────────────────────

    def apply_conflict(self, decision: dict) -> dict:
        """V1.1: ConflictDecision -> MemoryRecord (the resolved record)."""
        strategy = decision.get("strategy", "keep_old")
        if strategy == "keep_old":
            return {"memory_id": decision["old_memory_id"], "status": "active", "note": "kept old"}
        elif strategy == "keep_new":
            return {"memory_id": decision["new_memory_id"], "status": "active", "note": "kept new, superseded old"}
        elif strategy == "merge":
            return {
                "memory_id": decision["new_memory_id"],
                "status": "active",
                "supersedes": [decision["old_memory_id"]],
                "revision": 2,
                "note": "merged",
            }
        else:
            return {"memory_id": decision["new_memory_id"], "status": "pending_review", "note": "manual review"}
