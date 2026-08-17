"""Frozen HybridRetriever adapter for Algorithm V1.1."""

from __future__ import annotations

import os
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
        self._no_answer_rejection_enabled = _config_bool(
            config,
            "no_answer_rejection_enabled",
            False,
        )
        self._no_answer_score_threshold = _config_float(
            config,
            "no_answer_score_threshold",
            0.69,
        )
        self._no_answer_margin_threshold = _config_float(
            config,
            "no_answer_margin_threshold",
            0.015,
        )

    def search(self, request: SearchRequest) -> SearchResponse:
        request = SearchRequest.model_validate(request)
        candidate_k = max(request.top_k, int(self._candidate_k))
        raw_request = {
            "request_id": request.request_id,
            "user_id": request.user_id,
            "query": request.query,
            "top_k": request.top_k,
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
        meta = raw.get("meta", {})
        if not isinstance(meta, Mapping):
            meta = {}
        if _should_reject_no_answer(
            raw_items,
            enabled=self._no_answer_rejection_enabled,
            degraded=bool(meta.get("degraded", False)),
            score_threshold=self._no_answer_score_threshold,
            margin_threshold=self._no_answer_margin_threshold,
        ):
            raw_items = []

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
        stale_memory_ids = [
            memory_id
            for memory_id in memory_ids
            if memory_id not in records_by_id
        ]
        if stale_memory_ids:
            with self.runtime.lock:
                self.runtime.remove_bm25(stale_memory_ids)
        items: list[SearchHit] = []
        for memory_id in memory_ids:
            record = records_by_id.get(memory_id)
            if record is None or not _matches_filters(record, request.filters):
                continue
            public_attributes = dict(record.attributes)
            public_attributes.pop("embedding", None)
            items.append(
                SearchHit(
                    memory_id=record.memory_id,
                    user_id=record.user_id,
                    status=record.status,
                    content_text=record.content_text,
                    score=scores[memory_id],
                    attributes=public_attributes,
                )
            )
            if len(items) >= request.top_k:
                break

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
    environment_name = f"OS_AGENT_ALGORITHM_RETRIEVAL__{name.upper()}"
    environment_value = os.getenv(environment_name)
    if environment_value is not None:
        return environment_value
    if isinstance(config, Mapping):
        return config.get(name, default)
    return getattr(config, name, default)


def _config_bool(config: Any, name: str, default: bool) -> bool:
    value = _config_value(config, name, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _config_float(config: Any, name: str, default: float) -> float:
    value = float(_config_value(config, name, default))
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"retrieval {name} must be between 0 and 1")
    return value


def _should_reject_no_answer(
    raw_items: list[Any],
    *,
    enabled: bool,
    degraded: bool,
    score_threshold: float,
    margin_threshold: float,
) -> bool:
    """Apply the optional dense-score abstention rule.

    The rule is deliberately disabled by default because Dataset V0.1 dev
    contains only one no-answer query. It is also never applied to BM25
    fallback scores, whose scale is not comparable with cosine similarity.
    """
    if not enabled or degraded or len(raw_items) < 2:
        return False
    first, second = raw_items[0], raw_items[1]
    if not isinstance(first, Mapping) or not isinstance(second, Mapping):
        return False
    try:
        top1 = float(first.get("score", 0.0))
        top2 = float(second.get("score", 0.0))
    except (TypeError, ValueError):
        return False
    return top1 < score_threshold and (top1 - top2) < margin_threshold


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
