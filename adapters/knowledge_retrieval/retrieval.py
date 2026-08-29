"""Frozen HybridRetriever adapter for Algorithm V1.1."""

from __future__ import annotations

import re
from typing import Any, Mapping

from contracts.schemas.common import MemoryStatus
from contracts.schemas.memory import MemoryRecord
from contracts.schemas.retrieval import SearchHit, SearchRequest, SearchResponse

from .knowledge import KnowledgeServiceAdapter
from .runtime import KnowledgeRetrievalRuntime


class HybridRetrieverAdapter:
    """Run donor dense/BM25 fusion, then hydrate from the repository."""

    def __init__(
        self,
        embedding_provider: Any,
        vector_store: Any,
        memory_repository: Any,
        knowledge_service: Any = None,
        config: Any = None,
        app_config: Any = None,
    ) -> None:
        del app_config
        if isinstance(knowledge_service, KnowledgeServiceAdapter):
            self.runtime = knowledge_service.runtime
        else:
            self.runtime = KnowledgeRetrievalRuntime(
                embedding_provider,
                vector_store,
            )
        self._repository = memory_repository
        self._candidate_k = _config_value(config, "candidate_k", 30)

    def search(self, request: SearchRequest) -> SearchResponse:
        request = SearchRequest.model_validate(request)
        candidate_k = max(request.top_k, int(self._candidate_k))
        raw_request = {
            "request_id": request.request_id,
            "user_id": request.user_id,
            "query": request.query,
            "top_k": candidate_k,
            "candidate_k": candidate_k,
            "filters": dict(request.filters),
        }
        with self.runtime.lock:
            raw = self.runtime.hybrid.search(raw_request)
        if not isinstance(raw, Mapping):
            raise TypeError("algorithm retriever returned a non-mapping response")
        raw_items = raw.get("items", [])
        if not isinstance(raw_items, list):
            raise TypeError("algorithm retriever returned invalid items")

        memory_ids: list[str] = []
        scores: dict[str, float] = {}
        for item in raw_items:
            if not isinstance(item, Mapping):
                continue
            memory_id = str(item.get("memory_id", "")).strip()
            if not memory_id:
                continue
            if memory_id not in scores:
                memory_ids.append(memory_id)
                scores[memory_id] = float(item.get("score", 0.0))
            else:
                scores[memory_id] = max(
                    scores[memory_id],
                    float(item.get("score", 0.0)),
                )

        records = self._repository.get_by_ids(
            request.user_id,
            memory_ids,
            [MemoryStatus.ACTIVE],
        )
        records_by_id = {
            record.memory_id: MemoryRecord.model_validate(record)
            for record in records
        }
        ranked_records: list[tuple[MemoryRecord, float]] = []
        for memory_id in memory_ids:
            record = records_by_id.get(memory_id)
            if record is None or not _matches_filters(record, request.filters):
                continue
            ranked_records.append((record, scores[memory_id]))

        ranked_records.sort(
            key=lambda entry: _rerank_key(request.query, entry[0], entry[1]),
            reverse=True,
        )
        items: list[SearchHit] = [
            SearchHit(
                memory_id=record.memory_id,
                user_id=record.user_id,
                status=record.status,
                content_text=record.content_text,
                score=score,
                attributes=dict(record.attributes),
            )
            for record, score in ranked_records[: request.top_k]
        ]

        meta = raw.get("meta", {})
        if not isinstance(meta, Mapping):
            meta = {}
        return SearchResponse(
            request_id=request.request_id,
            user_id=request.user_id,
            items=items,
            total=len(items),
            provider="algorithm-v1.1-hybrid",
            degraded=bool(meta.get("degraded", False)),
        )


def build_hybrid_retriever(
    embedding_provider: Any,
    vector_store: Any,
    memory_repository: Any,
    knowledge_service: Any = None,
    config: Any = None,
    app_config: Any = None,
) -> HybridRetrieverAdapter:
    return HybridRetrieverAdapter(
        embedding_provider=embedding_provider,
        vector_store=vector_store,
        memory_repository=memory_repository,
        knowledge_service=knowledge_service,
        config=config,
        app_config=app_config,
    )


def _config_value(config: Any, name: str, default: Any) -> Any:
    if isinstance(config, Mapping):
        return config.get(name, default)
    return getattr(config, name, default)


_TECHNICAL_TOKEN_PATTERN = re.compile(
    r"(?<![0-9A-Za-z_])"
    r"(?:--?[0-9A-Za-z]+(?:\s*[_+./:-]\s*[0-9A-Za-z]+)*"
    r"|[0-9A-Za-z]+(?:\s*[_+./:-]\s*[0-9A-Za-z]+)+)"
    r"(?![0-9A-Za-z_])"
)


def _matches_filters(
    record: MemoryRecord,
    filters: Mapping[str, Any],
) -> bool:
    for key, expected in filters.items():
        if key == "memory_kind":
            actual = record.memory_kind.value
        elif key == "subtype":
            actual = record.subtype.value
        elif key in {"scene", "scene_tag"}:
            if expected not in record.scene_tags:
                return False
            continue
        elif key == "status":
            actual = record.status.value
        else:
            actual = record.attributes.get(key)
        if actual != expected:
            return False
    return True


def _technical_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for token in _TECHNICAL_TOKEN_PATTERN.findall(text):
        normalized = re.sub(r"\s+", "", token).casefold()
        if any(character.isalnum() for character in normalized):
            tokens.add(normalized)
    return tokens


def _searchable_text(record: MemoryRecord) -> str:
    scalar_attributes = " ".join(
        str(value)
        for value in record.attributes.values()
        if isinstance(value, (str, int, float, bool))
    )
    return re.sub(
        r"\s+",
        "",
        " ".join(
            [
                record.content_text,
                str(record.content),
                scalar_attributes,
            ]
        ).casefold(),
    )


def _rerank_key(
    query: str,
    record: MemoryRecord,
    base_score: float,
) -> tuple[int, int, float]:
    query_tokens = _technical_tokens(query)
    if not query_tokens:
        return (0, 0, base_score)

    searchable_text = _searchable_text(record)
    matched_tokens = sum(token in searchable_text for token in query_tokens)
    full_match = int(matched_tokens == len(query_tokens))
    return (full_match, matched_tokens, base_score)
