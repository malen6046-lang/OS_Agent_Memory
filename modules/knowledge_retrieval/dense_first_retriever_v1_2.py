"""V1.2 dense-first retrieval with BM25 fallback.

This module keeps the immutable V1.1 RRF donor intact while preserving the
ranking strategy validated against the Kylin GTE embedding SDK.
"""

from __future__ import annotations

import time
from typing import Any


class DenseFirstRetrieverV12:
    """Use dense SDK ranking and fall back to BM25 only on provider failure."""

    def __init__(self, embedding_provider: Any, vector_store: Any, bm25: Any):
        self._emb = embedding_provider
        self._vs = vector_store
        self._bm25 = bm25
        self._degraded = False

    def search(self, request: dict[str, Any]) -> dict[str, Any]:
        if hasattr(request, "model_dump"):
            request = request.model_dump()
        if isinstance(request, dict) and "payload" in request:
            request = request["payload"]

        started_at = time.perf_counter()
        query = str(request.get("query", "")).strip()
        if not query:
            return {
                "items": [],
                "meta": {
                    "elapsed_ms": 0.0,
                    "degraded": False,
                    "embedding_provider": "none",
                    "vector_provider": "none",
                    "retrieval_mode": "empty_query",
                    "candidate_count": 0,
                },
            }

        top_k = max(1, int(request.get("top_k", 5)))
        candidate_k = max(top_k, int(request.get("candidate_k", 30)))
        user_id = str(request.get("user_id", "")).strip()
        if not user_id:
            raise ValueError("user_id is required for search")

        self._degraded = False
        dense: list[dict[str, Any]] = []
        try:
            health = self._emb.health()
            if health.get("status") == "stopped":
                raise RuntimeError("embedding stopped")
            batch = self._emb.encode([query])
            if not batch.get("vectors"):
                raise RuntimeError("empty embedding result")
            dense_raw = self._vs.query(
                {
                    "vector": batch["vectors"][0],
                    "top_k": candidate_k,
                    "filter_user_id": user_id,
                    "filter_status": "active",
                }
            )
            dense = [self._dense_item(item) for item in dense_raw]
        except Exception:
            self._degraded = True

        sparse: list[dict[str, Any]] = []
        if self._degraded:
            sparse = self._bm25.search(
                query,
                top_k=candidate_k,
                filter_user_id=user_id,
                filter_status="active",
            )
            ranked = [self._sparse_item(item) for item in sparse[:top_k]]
            retrieval_mode = "bm25_fallback"
        else:
            ranked = dense[:top_k]
            retrieval_mode = "dense"

        return {
            "items": [self._public_item(item) for item in ranked],
            "meta": {
                "elapsed_ms": round(
                    (time.perf_counter() - started_at) * 1000,
                    1,
                ),
                "degraded": self._degraded,
                "embedding_provider": (
                    "none" if self._degraded else self._embedding_name()
                ),
                "vector_provider": "none" if self._degraded else "configured",
                "retrieval_mode": retrieval_mode,
                "candidate_count": len(dense) + len(sparse),
            },
        }

    @staticmethod
    def _dense_item(item: dict[str, Any]) -> dict[str, Any]:
        metadata = item.get("meta", {})
        memory_id = metadata.get("memory_id", str(item["vector_pk"]))
        return {
            "doc_id": memory_id,
            "memory_id": memory_id,
            "score": item["score"],
            "meta": metadata,
        }

    @staticmethod
    def _sparse_item(item: dict[str, Any]) -> dict[str, Any]:
        metadata = item.get("meta", {})
        memory_id = metadata.get("memory_id", item["doc_id"])
        return {
            "doc_id": item["doc_id"],
            "memory_id": memory_id,
            "score": item["score"],
            "meta": metadata,
        }

    @staticmethod
    def _public_item(item: dict[str, Any]) -> dict[str, Any]:
        metadata = item.get("meta", {})
        return {
            "memory_id": item.get("memory_id", item.get("doc_id", "")),
            "score": item.get("score", 0.0),
            "memory_kind": metadata.get("memory_kind", "semantic"),
            "content_text": metadata.get("content_text", ""),
            "metadata": metadata,
        }

    def _embedding_name(self) -> str:
        try:
            return str(self._emb.model_info().get("model_name", "unknown"))
        except Exception:
            return "unknown"
