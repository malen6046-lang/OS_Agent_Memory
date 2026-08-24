"""Shared runtime bridges for the Algorithm V1.1 retrieval core."""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock
from typing import Any, Mapping

from contracts.schemas.common import MemoryStatus
from contracts.schemas.provider import VectorQuery
from modules.knowledge_retrieval.algorithm_v1_1.bm25 import BM25Retriever
from modules.knowledge_retrieval.dense_first_retriever_v1_2 import (
    DenseFirstRetrieverV12,
)
from modules.knowledge_retrieval.memory_flow_v1_2 import MemoryFlowController


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

    def __init__(
        self,
        embedding_provider: Any,
        vector_store: Any,
        *,
        bm25_state_path: str | os.PathLike[str] | None = None,
    ) -> None:
        self.lock = RLock()
        self.embedding = AlgorithmEmbeddingBridge(embedding_provider)
        self.vector = AlgorithmVectorQueryBridge(vector_store)
        self.bm25 = BM25Retriever()
        self.memory_flow = MemoryFlowController()
        self._documents: dict[str, dict[str, Any]] = {}
        self._bm25_state = (
            _BM25State(Path(bm25_state_path))
            if bm25_state_path is not None
            else None
        )
        if self._bm25_state is not None:
            documents = self._bm25_state.load()
            if documents:
                self.bm25.index(documents)
                self._documents.update(
                    {document["doc_id"]: dict(document) for document in documents}
                )
        self.hybrid = DenseFirstRetrieverV12(
            self.embedding,
            self.vector,
            self.bm25,
        )

    def index_bm25(self, documents: list[dict[str, Any]]) -> None:
        """Index documents and persist the process-local sparse state."""
        self.bm25.index(documents)
        self._documents.update(
            {document["doc_id"]: dict(document) for document in documents}
        )
        if self._bm25_state is not None:
            self._bm25_state.upsert(documents)

    def remove_bm25(self, memory_ids: list[str]) -> None:
        """Drop repository-confirmed stale candidates from sparse state."""
        unique_ids = list(dict.fromkeys(memory_ids))
        for memory_id in unique_ids:
            self.bm25.remove(memory_id)
            self._documents.pop(memory_id, None)
            self.memory_flow.remove(memory_id)
        if self._bm25_state is not None:
            self._bm25_state.remove(unique_ids)

    def documents_for_user(self, user_id: str) -> list[dict[str, Any]]:
        """Return active sparse documents for bounded forget previews."""
        return [
            dict(document)
            for document in self._documents.values()
            if document.get("user_id") == user_id
            and document.get("status") == MemoryStatus.ACTIVE.value
        ]


class _BM25State:
    """Persist only the minimal documents needed to rebuild donor BM25."""

    _VERSION = 1
    _FIELDS = (
        "doc_id",
        "text",
        "content_text",
        "user_id",
        "memory_kind",
        "status",
    )

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()
        self._documents: dict[str, dict[str, Any]] = {}

    def load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"cannot load BM25 state {self.path}: {exc}"
            ) from exc
        if not isinstance(payload, Mapping) or payload.get("version") != self._VERSION:
            raise RuntimeError(f"unsupported BM25 state format: {self.path}")
        documents = payload.get("documents")
        if not isinstance(documents, list):
            raise RuntimeError(f"invalid BM25 documents: {self.path}")
        for raw in documents:
            document = self._validate(raw)
            self._documents[document["doc_id"]] = document
        return list(self._documents.values())

    def upsert(self, documents: list[dict[str, Any]]) -> None:
        for raw in documents:
            document = self._validate(raw)
            self._documents[document["doc_id"]] = document
        self._write()

    def remove(self, memory_ids: list[str]) -> None:
        changed = False
        for memory_id in memory_ids:
            if self._documents.pop(memory_id, None) is not None:
                changed = True
        if changed:
            self._write()

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            self.path.parent.chmod(0o700)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        payload = {
            "version": self._VERSION,
            "documents": list(self._documents.values()),
        }
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        if os.name == "posix":
            temporary.chmod(0o600)
        os.replace(temporary, self.path)

    def _validate(self, raw: Any) -> dict[str, Any]:
        if not isinstance(raw, Mapping):
            raise RuntimeError("BM25 document must be a mapping")
        document = {field: raw.get(field) for field in self._FIELDS}
        doc_id = document["doc_id"]
        if not isinstance(doc_id, str) or not doc_id.strip():
            raise RuntimeError("BM25 document requires a non-empty doc_id")
        for field in ("text", "content_text", "user_id", "memory_kind", "status"):
            value = document[field]
            if not isinstance(value, str):
                raise RuntimeError(f"BM25 document {field} must be a string")
        document["doc_id"] = doc_id.strip()
        return document


def _dump(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="python")
    raise TypeError(f"unsupported provider response: {type(value).__name__}")


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)
