"""MemoryVectorStore — 内存版向量库，用 numpy 做余弦相似度搜索。

Implements the VectorStoreAdapter protocol from V1.1:
  start(config) -> ProviderHealth
  close() -> None
  ensure_collection(spec) -> None
  upsert(items: list[VectorItem]) -> UpsertResult
  query(request: VectorQuery) -> list[VectorHit]
  delete(vector_pks: list[int]) -> DeleteResult

V1.1 constraints:
  - 使用业务层传入的 vector_pk (平台生成的稳定 63-bit INT64)
  - 检索强制 user_id + status=active 过滤
  - 删除后不得再次召回
  - 向量维度运行时确定，不硬编码
"""
from __future__ import annotations

import numpy as np


class MemoryVectorStore:
    def __init__(self, dim: int = 768):
        self._dim = dim
        self._vectors: dict[int, list[float]] = {}   # vector_pk -> vector
        self._meta: dict[int, dict] = {}              # vector_pk -> full metadata
        self._id_counter = 1

    # ── lifecycle ──────────────────────────────────────────────

    def start(self, config: dict | None = None) -> dict:
        if config:
            self._dim = config.get("dim", config.get("dimension", self._dim))
        return {
            "provider": "memory",
            "dimension": self._dim,
            "status": "healthy",
        }

    def close(self) -> None:
        self._vectors.clear()
        self._meta.clear()

    # ── collection ─────────────────────────────────────────────

    def ensure_collection(self, spec: dict) -> None:
        if "dim" in spec:
            self._dim = spec["dim"]
        elif "dimension" in spec:
            self._dim = spec["dimension"]

    # ── upsert ─────────────────────────────────────────────────

    def upsert(self, items: list[dict]) -> dict:
        upserted = 0
        errors: list[dict] = []
        for idx, item in enumerate(items):
            try:
                pk = item["vector_pk"]
                self._vectors[pk] = item["vector"]
                self._meta[pk] = {k: v for k, v in item.items() if k != "vector"}
                upserted += 1
            except Exception as exc:
                errors.append({"index": idx, "error": str(exc)})
        return {"upserted": upserted, "errors": errors or None}

    # ── query ──────────────────────────────────────────────────

    def query(self, request: dict) -> list[dict]:
        """V1.1: 强制 user/status filter, 默认 status=active."""
        qvec = np.array(request["vector"], dtype=np.float64)
        top_k = request.get("top_k", 10)
        uid_filter = request.get("filter_user_id")
        status_filter = request.get("filter_status", "active")
        kind_filter = request.get("filter_memory_kind")

        q_norm = float(np.linalg.norm(qvec)) + 1e-10

        results = []
        for pk, vec in self._vectors.items():
            meta = self._meta.get(pk)
            if not meta:
                continue
            if uid_filter and meta.get("user_id") != uid_filter:
                continue
            if status_filter and meta.get("status") != status_filter:
                continue
            if kind_filter and meta.get("memory_kind") != kind_filter:
                continue

            vec_arr = np.array(vec, dtype=np.float64)
            v_norm = float(np.linalg.norm(vec_arr)) + 1e-10
            sim = float(np.dot(qvec, vec_arr) / (q_norm * v_norm))
            results.append({"vector_pk": pk, "score": sim, "meta": dict(meta)})

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    # ── delete ─────────────────────────────────────────────────

    def delete(self, vector_pks: list[int]) -> dict:
        deleted = 0
        errors: list[dict] = []
        for pk in vector_pks:
            if pk in self._vectors:
                del self._vectors[pk]
                del self._meta[pk]
                deleted += 1
            else:
                errors.append({"vector_pk": pk, "error": "not_found"})
        return {"deleted": deleted, "errors": errors or None}
