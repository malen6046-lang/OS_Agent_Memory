"""KnowledgeService — 知识写入、去重、冲突候选检测。"""
from __future__ import annotations
import uuid
from typing import Any


class KnowledgeService:
    def __init__(self, embedding_provider: Any, vector_store: Any, bm25: Any,
                 metadata_store: dict | None = None):
        self._emb = embedding_provider
        self._vs = vector_store
        self._bm25 = bm25
        self._meta: dict[str, dict] = metadata_store if metadata_store is not None else {}

    def ingest(self, records: list[dict]) -> dict:
        all_indexed = []
        ingest_errors = []
        for idx, rec in enumerate(records):
            try:
                title = rec.get("title", rec.get("content_text", ""))
                body = rec.get("body", rec.get("content_text", ""))
                text = (title + " " + body).strip()
                if not text:
                    ingest_errors.append({"index": idx, "error": "empty_text"})
                    continue
                result = self._ingest_one(rec, text)
                all_indexed.append({
                    "status": result["action"],
                    "memory_id": result["memory_id"],
                    "indexed": result.get("indexed", {}),
                    "errors": result.get("errors"),
                })
            except Exception as exc:
                ingest_errors.append({"index": idx, "error": str(exc)})
        return {
            "items": all_indexed,
            "errors": ingest_errors or None,
        }

    def _ingest_one(self, rec: dict, text: str) -> dict:
        user_id = rec.get("user_id", "default")
        candidates = self._find_similar(text, user_id)
        threshold = 0.85
        # Conflict detection
        for cand in candidates:
            cand_text = cand["meta"].get("content_text", "")
            score = cand["score"]
            if score >= threshold:
                if cand_text == text:
                    return {"action": "duplicate", "memory_id": cand["meta"].get("memory_id", "")}
                old_id = cand["meta"].get("memory_id", "")
                old_version = cand["meta"].get("revision", 1)
                new_version = old_version + 1
                memory_id = f"mem_{uuid.uuid4().hex[:16]}"
                idx_result = self._write_to_stores(memory_id, rec, text, user_id)
                return {"action": "conflict", "memory_id": memory_id,
                        "old_memory_id": old_id, "new_version": new_version,
                        "indexed": idx_result["indexed"], "errors": idx_result["errors"]}
        memory_id = f"mem_{uuid.uuid4().hex[:16]}"
        idx_result = self._write_to_stores(memory_id, rec, text, user_id)
        return {"action": "inserted", "memory_id": memory_id,
                "indexed": idx_result["indexed"], "errors": idx_result["errors"]}

    def _write_to_stores(self, memory_id: str, rec: dict, text: str, user_id: str) -> dict:
        """Write to metadata, BM25, and vector store. Returns indexed status per store."""
        doc = {
            "doc_id": memory_id,
            "memory_id": memory_id,
            "text": text,
            "content_text": text,
            "user_id": user_id,
            "memory_kind": rec.get("memory_kind", "semantic"),
            "subtype": rec.get("subtype", rec.get("knowledge_type", "fact")),
            "content": rec,
            "confidence": rec.get("source_reliability", rec.get("confidence", 0.8)),
            "importance": rec.get("importance", rec.get("source_reliability", 0.8)),
            "revision": rec.get("revision", 1),
            "valid_from": rec.get("effective_at", rec.get("valid_from")),
            "source_refs": [rec.get("source_event_id", "")],
            "status": rec.get("status", "active"),
            "scene": rec.get("scene", "default"),
        }
        indexed = {"metadata": False, "bm25": False, "vector": False}
        errors: list[str] = []

        # Metadata
        try:
            self._meta[memory_id] = doc
            indexed["metadata"] = True
        except Exception as e:
            errors.append(f"metadata: {e}")

        # BM25
        if self._bm25:
            try:
                self._bm25.index([doc])
                indexed["bm25"] = True
            except Exception as e:
                errors.append(f"bm25: {e}")

        # Vector store
        if self._emb:
            try:
                batch = self._emb.encode([text])
                vectors = batch.get("vectors", [])
                if vectors:
                    import hashlib
                    pk = int(hashlib.md5(memory_id.encode()).hexdigest(), 16) & 0x7FFFFFFFFFFFFFFF
                    result = self._vs.upsert([{
                        "vector_pk": pk,
                        "vector": vectors[0],
                        **{
                            key: value
                            for key, value in doc.items()
                            if key not in {"doc_id", "text"}
                        },
                    }])
                    if result.get("errors"):
                        errors.append(f"vector: {result['errors']}")
                    else:
                        indexed["vector"] = True
            except Exception as e:
                errors.append(f"vector: {e}")

        return {"indexed": indexed, "errors": errors or None}

    def _find_similar(self, text: str, user_id: str) -> list[dict]:
        try:
            health = self._emb.health()
            if health.get("status") == "stopped":
                return []
            batch = self._emb.encode([text])
            vectors = batch.get("vectors", [])
            if not vectors:
                return []
            return self._vs.query({"vector": vectors[0], "top_k": 3,
                                   "filter_user_id": user_id, "filter_status": "active"})
        except Exception:
            return []

    def classify_conflict(self, old: dict, new: dict) -> dict:
        old_text = old.get("content_text", "")
        new_text = new.get("content_text", "")
        if old_text == new_text:
            return self._make_decision("duplicate", old, new, ["same_text"])
        old_kind = old.get("memory_kind", "")
        new_kind = new.get("memory_kind", "")
        if old_kind == new_kind and self._is_contradictory(old, new):
            return self._make_decision("contradict", old, new, ["same_entity", "contradictory_values"])
        if old_kind == new_kind and self._same_entity(old_text, new_text):
            old_eff = old.get("valid_from", "")
            new_eff = new.get("valid_from", "")
            if new_eff and old_eff and new_eff >= old_eff:
                return self._make_decision("replace", old, new, ["same_entity", "same_attribute", "newer_effective_at"])
        if old_kind == new_kind and self._overlapping_topic(old_text, new_text):
            return self._make_decision("extend", old, new, ["same_entity", "complementary"])
        return self._make_decision("unrelated", old, new, ["low_similarity"])

    def _same_entity(self, t1: str, t2: str) -> bool:
        t1_set, t2_set = set(t1), set(t2)
        if not t1_set or not t2_set:
            return False
        return len(t1_set & t2_set) / min(len(t1_set), len(t2_set)) > 0.3

    def _overlapping_topic(self, t1: str, t2: str) -> bool:
        return self._same_entity(t1, t2)

    def _is_contradictory(self, old: dict, new: dict) -> bool:
        t1 = old.get("content_text", "")
        t2 = new.get("content_text", "")
        if not t1 or not t2:
            return False
        if not self._same_entity(t1, t2):
            return False
        negations = ["不", "已废弃", "已更新为", "不可", "否", "非", "取消"]
        for neg in negations:
            if (neg in t1) != (neg in t2):
                return True
        c1, c2 = old.get("content", {}), new.get("content", {})
        if isinstance(c1, dict) and isinstance(c2, dict) and c1 and c2:
            for k in set(c1.keys()) & set(c2.keys()):
                if c1[k] != c2[k]:
                    return True
        return False

    def _make_decision(self, relation: str, old: dict, new: dict, reasons: list[str]) -> dict:
        strategy_map = {"duplicate": "keep_old", "support": "merge", "extend": "merge",
                        "replace": "keep_new", "contradict": "manual_review", "unrelated": "keep_old"}
        return {"relation": relation, "old_memory_id": old.get("memory_id", ""),
                "new_memory_id": new.get("memory_id", ""),
                "confidence": 0.89 if relation in ("replace", "contradict") else 0.85,
                "strategy": strategy_map.get(relation, "manual_review"),
                "reason_codes": reasons, "detail": None}

    def apply_conflict(self, decision: dict) -> dict:
        strategy = decision.get("strategy", "keep_old")
        if strategy == "keep_old":
            return {"memory_id": decision["old_memory_id"], "status": "active"}
        elif strategy == "keep_new":
            return {"memory_id": decision["new_memory_id"], "status": "active"}
        elif strategy == "merge":
            return {"memory_id": decision["new_memory_id"], "status": "active",
                    "supersedes": [decision["old_memory_id"]], "revision": 2}
        else:
            return {"memory_id": decision["new_memory_id"], "status": "pending_review"}
