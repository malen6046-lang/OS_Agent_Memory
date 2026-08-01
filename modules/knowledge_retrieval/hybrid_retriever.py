"""HybridRetriever — dense向量 + BM25 用 RRF 融合，向量不可用时降级为 BM25。"""
from __future__ import annotations
import time
from typing import Any


class HybridRetriever:
    def __init__(self, embedding_provider: Any, vector_store: Any, bm25: Any):
        self._emb = embedding_provider
        self._vs = vector_store
        self._bm25 = bm25
        self._degraded = False

    def _rrf(self, dense: list[dict], sparse: list[dict], top_k: int, k: int = 60) -> list[dict]:
        merged: dict[str, dict] = {}
        for rank, item in enumerate(dense):
            pid = item.get("doc_id", item.get("memory_id", ""))
            merged[pid] = {**item, "rrf": 1.0 / (k + rank + 1)}
        for rank, item in enumerate(sparse):
            pid = item.get("doc_id", item.get("memory_id", ""))
            if pid in merged:
                merged[pid]["rrf"] += 1.0 / (k + rank + 1)
            else:
                merged[pid] = {**item, "rrf": 1.0 / (k + rank + 1)}
            merged[pid]["score"] = merged[pid]["rrf"]
        ranked = sorted(merged.values(), key=lambda x: x["rrf"], reverse=True)
        return ranked[:top_k]

    def search(self, request: dict) -> dict:
        if hasattr(request, "model_dump"):
            request = request.model_dump()
        if isinstance(request, dict) and "payload" in request:
            request = request["payload"]
        t0 = time.time()
        query: str = request.get("query", "")
        if not query:
            return {"items": [], "meta": {"elapsed_ms": 0, "degraded": False,
                     "embedding_provider": "none", "vector_provider": "none", "candidate_count": 0}}
        top_k: int = request.get("top_k", 5)
        candidate_k: int = request.get("candidate_k", 30)
        uid: str | None = request.get("user_id")
        if not uid:
            raise ValueError("user_id is required for search")
        self._degraded = False

        sparse = self._bm25.search(query, top_k=candidate_k, filter_user_id=uid, filter_status="active")

        dense: list[dict] = []
        try:
            health = self._emb.health()
            if health.get("status") == "stopped":
                raise RuntimeError("embedding stopped")
            batch = self._emb.encode([query])
            if not batch.get("vectors"):
                raise RuntimeError("empty embedding result")
            qvec = batch["vectors"][0]
            dense_raw = self._vs.query({
                "vector": qvec, "top_k": candidate_k,
                "filter_user_id": uid, "filter_status": "active",
            })
            for item in dense_raw:
                meta = item.get("meta", {})
                dense.append({
                    "doc_id": meta.get("memory_id", str(item["vector_pk"])),
                    "memory_id": meta.get("memory_id", str(item["vector_pk"])),
                    "score": item["score"], "meta": meta,
                })
        except Exception:
            self._degraded = True

        if dense:
            final = self._rrf(dense, sparse, top_k)
        else:
            self._degraded = True
            final = [{"doc_id": s["doc_id"], "memory_id": s["meta"].get("memory_id", s["doc_id"]),
                       "score": s["score"], "meta": s["meta"]} for s in sparse[:top_k]]

        items = []
        for entry in final:
            meta = entry.get("meta", {})
            items.append({
                "memory_id": entry.get("memory_id", entry.get("doc_id", "")),
                "score": entry.get("score", 0.0),
                "memory_kind": meta.get("memory_kind", "semantic"),
                "content_text": meta.get("content_text", ""),
                "metadata": meta,
            })

        elapsed = (time.time() - t0) * 1000
        emb_provider = "none"
        vs_provider = "none"
        try:
            emb_provider = self._emb.model_info().get("model_name", "none")
        except Exception:
            pass
        try:
            vs_provider = self._emb.model_info().get("model_name", "fallback") if self._degraded else "fallback"
        except Exception:
            vs_provider = "memory"

        return {
            "items": items,
            "meta": {
                "elapsed_ms": round(elapsed, 1),
                "degraded": self._degraded,
                "embedding_provider": emb_provider if not self._degraded else "none",
                "vector_provider": vs_provider,
                "candidate_count": len(sparse) + len(dense),
            },
        }
