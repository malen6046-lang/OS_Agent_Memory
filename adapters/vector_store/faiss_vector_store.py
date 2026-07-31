"""FaissVectorStore — FAISS 向量库 fallback。

Implements the VectorStoreAdapter protocol from V1.1:
  start(config) -> ProviderHealth
  close() -> None
  ensure_collection(spec) -> None
  upsert(items) -> UpsertResult
  query(request) -> list[VectorHit]
  delete(vector_pks) -> DeleteResult

Uses FAISS IndexFlatIP for inner-product similarity (equivalent to cosine
with normalized vectors).
"""
from __future__ import annotations

import numpy as np


class FaissVectorStore:
    def __init__(self, dim: int = 768):
        self._dim = dim
        self._index = None
        self._pk_to_idx: dict[int, int] = {}
        self._idx_to_pk: list[int] = []
        self._meta: dict[int, dict] = {}
        self._deleted: set[int] = set()

    def start(self, config: dict | None = None) -> dict:
        if config:
            self._dim = config.get("dim", config.get("dimension", self._dim))
        try:
            import faiss
            self._index = faiss.IndexFlatIP(self._dim)
        except ImportError:
            self._index = None
            return {"provider": "faiss", "status": "degraded", "dimension": self._dim,
                    "detail": "faiss not installed, falling back to numpy"}
        return {"provider": "faiss", "status": "healthy", "dimension": self._dim}

    def close(self) -> None:
        self._index = None
        self._pk_to_idx.clear()
        self._idx_to_pk.clear()
        self._meta.clear()
        self._deleted.clear()

    def ensure_collection(self, spec: dict) -> None:
        dim = spec.get("dim", spec.get("dimension", 0))
        if dim and dim != self._dim:
            self._dim = dim
            import faiss
            self._index = faiss.IndexFlatIP(self._dim)

    def upsert(self, items: list[dict]) -> dict:
        upserted = 0
        errors = []
        vectors = []
        for idx, item in enumerate(items):
            try:
                pk = item["vector_pk"]
                vec = np.array(item["vector"], dtype=np.float32).reshape(1, -1)
                if self._index is not None:
                    import faiss
                    faiss.normalize_L2(vec)
                    i = self._index.ntotal
                    self._index.add(vec)
                else:
                    i = len(self._idx_to_pk)
                if pk in self._pk_to_idx:
                    old_i = self._pk_to_idx[pk]
                    self._idx_to_pk[old_i] = -1
                self._pk_to_idx[pk] = i
                if i >= len(self._idx_to_pk):
                    self._idx_to_pk.extend([-1] * (i - len(self._idx_to_pk) + 1))
                self._idx_to_pk[i] = pk
                self._meta[pk] = {"_vec": list(map(float, item["vector"])),
                                   **{k: v for k, v in item.items() if k != "vector"}}
                upserted += 1
            except Exception as exc:
                errors.append({"index": idx, "error": str(exc)})
        return {"upserted": upserted, "errors": errors or None}

    def query(self, request: dict) -> list[dict]:
        qvec_np = np.array(request["vector"], dtype=np.float64)
        top_k = request.get("top_k", 10)
        uid_filter = request.get("filter_user_id")
        status_filter = request.get("filter_status", "active")

        if self._index is not None and self._index.ntotal > 0:
            import faiss
            q = np.array(request["vector"], dtype=np.float32).reshape(1, -1)
            faiss.normalize_L2(q)
            f_top_k = min(top_k * 3, self._index.ntotal)
            scores, indices = self._index.search(q, f_top_k)
        else:
            all_scores = []
            for pk, meta in self._meta.items():
                vec = self._get_stored_vector(pk)
                if vec is None:
                    continue
                sim = float(np.dot(qvec_np, vec) / (np.linalg.norm(qvec_np) * np.linalg.norm(vec) + 1e-10))
                all_scores.append((pk, sim))
            all_scores.sort(key=lambda x: x[1], reverse=True)
            top = all_scores[:top_k * 3]
            indices = [[pk for pk, _ in top]]
            scores = [[s for _, s in top]]

        results = []
        for i, idx in enumerate(indices[0]):
            pk = idx if self._index is None else self._idx_to_pk[idx]
            meta = self._meta.get(pk)
            if not meta:
                continue
            if pk in self._deleted:
                continue
            if uid_filter and meta.get("user_id") != uid_filter:
                continue
            if status_filter and meta.get("status") != status_filter:
                continue
            kind_filter = request.get("filter_memory_kind")
            if kind_filter and meta.get("memory_kind") != kind_filter:
                continue
            results.append({"vector_pk": pk, "score": float(scores[0][i]), "meta": dict(meta)})
        return sorted(results, key=lambda x: x["score"], reverse=True)[:top_k]

    def _get_stored_vector(self, pk: int):
        meta = self._meta.get(pk)
        if not meta:
            return None
        for key in ("vector", "_vec"):
            v = meta.get(key)
            if v and isinstance(v, list):
                return np.array(v, dtype=np.float64)
        return None

    def delete(self, vector_pks: list[int]) -> dict:
        deleted = 0
        errors = []
        for pk in vector_pks:
            if pk in self._meta and pk not in self._deleted:
                self._deleted.add(pk)
                deleted += 1
            else:
                errors.append({"vector_pk": pk, "error": "not_found"})
        return {"deleted": deleted, "errors": errors or None}
