"""MemoryVectorStore — 内存版向量库，用 numpy 做余弦相似度搜索。

Implements the VectorStoreAdapter protocol from V1.1.
"""
from __future__ import annotations

import numpy as np


class MemoryVectorStore:
    def __init__(self, dim: int = 768):
        if dim <= 0:
            raise ValueError(f"dimension must be positive, got {dim}")
        self._dim = dim
        self._vectors: dict[int, list[float]] = {}
        self._meta: dict[int, dict] = {}
        self._started = False

    def start(self, config: dict | None = None) -> dict:
        if config:
            d = config.get("dim") or config.get("dimension")
            if d is not None and d > 0:
                self._dim = d
        self._started = True
        return {"provider": "memory", "dimension": self._dim, "status": "healthy"}

    def close(self) -> None:
        self._vectors.clear()
        self._meta.clear()
        self._started = False

    def ensure_collection(self, spec: dict) -> None:
        if "dim" in spec:
            self._dim = spec["dim"]
        elif "dimension" in spec:
            self._dim = spec["dimension"]

    def upsert(self, items: list[dict]) -> dict:
        upserted = 0
        errors: list[dict] = []
        for idx, item in enumerate(items):
            try:
                pk = item.get("vector_pk")
                if pk is None:
                    raise ValueError("vector_pk required")
                vec = item.get("vector")
                if vec is None or len(vec) == 0:
                    raise ValueError("vector must not be empty")
                if len(vec) != self._dim:
                    raise ValueError(f"dimension mismatch: expected {self._dim}, got {len(vec)}")
                uid = item.get("user_id", "").strip()
                if not uid:
                    raise ValueError("user_id required")
                st = item.get("status", "").strip()
                if not st:
                    raise ValueError("status required")
                self._vectors[pk] = vec
                self._meta[pk] = {k: v for k, v in item.items() if k != "vector"}
                upserted += 1
            except Exception as exc:
                errors.append({"index": idx, "error": str(exc)})
        return {"upserted": upserted, "errors": errors or None}

    def query(self, request: dict) -> list[dict]:
        qvec = np.array(request["vector"], dtype=np.float64)
        if qvec.size == 0 or qvec.shape[-1] != self._dim:
            raise ValueError(f"vector dimension mismatch: expected {self._dim}, got {qvec.shape[-1] if qvec.size else 0}")
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
