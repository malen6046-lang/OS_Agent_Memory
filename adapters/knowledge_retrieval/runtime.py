"""Shared runtime bridges for the Algorithm V1.1 retrieval core."""

from __future__ import annotations

from threading import RLock
from typing import Any, Mapping

from contracts.schemas.common import MemoryStatus
from contracts.schemas.provider import VectorQuery
from modules.knowledge_retrieval.algorithm_v1_1.bm25 import BM25Retriever
from modules.knowledge_retrieval.algorithm_v1_1.hybrid_retriever import (
    HybridRetriever as LegacyHybridRetriever,
)


class AlgorithmEmbeddingBridge:
    """Expose a frozen provider through the donor module's dict surface."""

    def __init__(self, provider: Any) -> None:
        self._provider = provider

    def health(self, deep: bool = False) -> dict[str, Any]:
        raw = _dump(self._provider.health(deep=deep))
        status = _enum_value(raw.get("status", "unavailable"))
        return {
            "provider": raw.get("provider", "unknown"),
            "status": status,
            "details": raw.get("details", {}),
        }

    def model_info(self) -> dict[str, Any]:
        raw = _dump(self._provider.model_info())
        return {
            "provider": raw.get("provider", "unknown"),
            "model_name": raw.get("model_name", "unknown"),
            "dimension": raw.get("dimension", 0),
            "fingerprint": raw.get("model_fingerprint"),
        }

    def encode(self, texts: list[str]) -> dict[str, Any]:
        raw = _dump(self._provider.encode(texts))
        return {
            "vectors": raw.get("vectors", []),
            "model_name": raw.get("model_name", "unknown"),
            "dimension": raw.get("dimension", 0),
        }


class AlgorithmVectorQueryBridge:
    """Translate donor vector queries to the frozen VectorStore protocol."""

    def __init__(self, vector_store: Any, *, timeout_ms: int = 500) -> None:
        self._vector_store = vector_store
        self._timeout_ms = timeout_ms

    def query(self, request: Mapping[str, Any]) -> list[dict[str, Any]]:
        user_id = str(
            request.get("filter_user_id", request.get("user_id", ""))
        ).strip()
        if not user_id:
            raise ValueError("algorithm vector query requires user_id")
        status = MemoryStatus(
            _enum_value(request.get("filter_status", MemoryStatus.ACTIVE))
        )
        top_k = max(1, min(100, int(request.get("top_k", 10))))
        filters = dict(request.get("filters", {}))
        memory_kind = request.get("filter_memory_kind")
        if memory_kind is not None:
            filters.setdefault("memory_kind", _enum_value(memory_kind))
        query = VectorQuery(
            user_id=user_id,
            status=status,
            vector=[float(value) for value in request["vector"]],
            top_k=top_k,
            timeout_ms=self._timeout_ms,
            filters=filters,
        )
        results: list[dict[str, Any]] = []
        for item in self._vector_store.query(query):
            hit = _dump(item)
            hit_status = _enum_value(hit.get("status", status))
            metadata = {
                "memory_id": hit.get("memory_id", ""),
                "user_id": hit.get("user_id", user_id),
                "status": hit_status,
            }
            results.append(
                {
                    "vector_pk": hit["vector_pk"],
                    "score": float(hit.get("score", 0.0)),
                    "meta": metadata,
                }
            )
        return results


class KnowledgeRetrievalRuntime:
    """One application-scoped donor BM25/retriever assembly."""

    def __init__(self, embedding_provider: Any, vector_store: Any) -> None:
        self.lock = RLock()
        self.embedding = AlgorithmEmbeddingBridge(embedding_provider)
        self.vector = AlgorithmVectorQueryBridge(vector_store)
        self.bm25 = BM25Retriever()
        self.hybrid = LegacyHybridRetriever(
            self.embedding,
            self.vector,
            self.bm25,
        )


def _dump(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="python")
    raise TypeError(f"unsupported provider response: {type(value).__name__}")


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)
