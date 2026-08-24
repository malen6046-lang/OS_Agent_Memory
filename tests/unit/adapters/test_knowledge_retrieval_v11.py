from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.dependencies.mock_services import (
    MockEmbeddingProvider,
    MockMemoryRepository,
    MockVectorStoreAdapter,
)
from adapters.knowledge_retrieval.knowledge import KnowledgeServiceAdapter
from adapters.knowledge_retrieval.retrieval import HybridRetrieverAdapter
from adapters.knowledge_retrieval.retrieval import _should_reject_no_answer
from contracts.schemas.common import MemoryStatus
from contracts.schemas.envelope import Envelope
from contracts.schemas.forget import ForgetExecutionPlan
from contracts.schemas.persistence import IngestServiceResult
from contracts.schemas.provider import VectorStoreConfig
from contracts.schemas.retrieval import SearchRequest
from modules.knowledge_retrieval.algorithm_v1_1.knowledge_service import (
    KnowledgeService as LegacyKnowledgeService,
)
from modules.knowledge_retrieval.dense_first_retriever_v1_2 import (
    DenseFirstRetrieverV12,
)


def _event(
    *,
    user_id: str = "user-1",
    source_event_id: str = "event-1",
    text: str = "用户喜欢深色主题",
    occurred_at: datetime | None = None,
) -> Envelope:
    return Envelope(
        contract_version="1.0",
        request_id=f"request-{source_event_id}",
        idempotency_key=f"idem-{source_event_id}",
        user_id=user_id,
        session_id=None,
        scene="desktop",
        source="user_behavior",
        source_event_id=source_event_id,
        occurred_at=occurred_at or datetime.now(timezone.utc),
        payload={"text": text, "knowledge_type": "fact"},
    )


def _runtime_services():
    embedding = MockEmbeddingProvider("deterministic-test")
    vector_store = MockVectorStoreAdapter()
    repository = MockMemoryRepository()
    embedding.start()
    vector_store.start(
        VectorStoreConfig(
            provider="memory",
            collection_name="test",
            expected_dimension=8,
        )
    )
    knowledge = KnowledgeServiceAdapter(embedding, vector_store)
    retriever = HybridRetrieverAdapter(
        embedding_provider=embedding,
        vector_store=vector_store,
        memory_repository=repository,
        knowledge_service=knowledge,
        config={"candidate_k": 30},
    )
    return embedding, vector_store, repository, knowledge, retriever


def _commit(repository, vector_store, result) -> None:
    committed = repository.commit_ingest(
        IngestServiceResult(preferences=[], knowledge=result)
    )
    vector_store.upsert(committed.vector_items)


def test_ingest_returns_frozen_record_without_legacy_storage_write(
    monkeypatch,
) -> None:
    _, _, _, knowledge, _ = _runtime_services()

    def forbidden_ingest(*args, **kwargs):
        raise AssertionError("legacy storage-writing ingest must not be called")

    monkeypatch.setattr(LegacyKnowledgeService, "ingest", forbidden_ingest)
    result = knowledge.ingest([_event()], [])

    assert len(result.records) == 1
    assert result.conflicts == []
    record = result.records[0]
    assert record.user_id == "user-1"
    assert record.status == MemoryStatus.ACTIVE
    assert len(record.attributes["embedding"]) == 8
    assert record.attributes["algorithm_source"].endswith("8c1e47d")


def test_memory_id_is_deterministic_per_user_source_and_index() -> None:
    _, _, _, knowledge, _ = _runtime_services()
    event = _event()

    first = knowledge.ingest([event], []).records[0]
    second = knowledge.ingest([event], []).records[0]

    assert first.memory_id == second.memory_id


def test_ingest_commit_vector_and_hybrid_search_round_trip() -> None:
    _, vector_store, repository, knowledge, retriever = _runtime_services()
    result = knowledge.ingest([_event()], [])
    _commit(repository, vector_store, result)

    response = retriever.search(
        SearchRequest(
            request_id="search-1",
            user_id="user-1",
            query="深色主题",
            top_k=5,
        )
    )

    assert response.request_id == "search-1"
    assert response.user_id == "user-1"
    assert response.provider == "algorithm-v1.1-hybrid"
    assert response.total == 1
    assert response.items[0].content_text == "用户喜欢深色主题"
    assert "embedding" not in response.items[0].attributes
    assert response.items[0].attributes["embedding_model"] == "deterministic-test"


def test_search_hydrates_with_user_and_active_status_boundary() -> None:
    _, vector_store, repository, knowledge, retriever = _runtime_services()
    own = knowledge.ingest([_event()], [])
    other = knowledge.ingest(
        [
            _event(
                user_id="user-2",
                source_event_id="event-2",
                text="用户喜欢深色主题",
            )
        ],
        [],
    )
    _commit(repository, vector_store, own)
    _commit(repository, vector_store, other)

    response = retriever.search(
        SearchRequest(
            request_id="search-user-boundary",
            user_id="user-1",
            query="深色主题",
            top_k=10,
        )
    )

    assert response.total == 1
    assert {item.user_id for item in response.items} == {"user-1"}


def test_search_applies_contract_filters_after_repository_hydration() -> None:
    _, vector_store, repository, knowledge, retriever = _runtime_services()
    result = knowledge.ingest([_event()], [])
    _commit(repository, vector_store, result)

    response = retriever.search(
        SearchRequest(
            request_id="search-filter",
            user_id="user-1",
            query="深色",
            top_k=5,
            filters={"subtype": "workflow"},
        )
    )

    assert response.items == []
    assert response.total == 0


def test_conflict_classifier_and_legacy_apply_are_contract_mapped() -> None:
    _, _, _, knowledge, _ = _runtime_services()
    now = datetime.now(timezone.utc)
    old = knowledge.ingest(
        [_event(occurred_at=now, text="界面使用深色主题")],
        [],
    ).records[0]
    new = knowledge.ingest(
        [
            _event(
                source_event_id="event-new",
                occurred_at=now + timedelta(seconds=1),
                text="界面使用浅色主题",
            )
        ],
        [],
    ).records[0]

    decision = knowledge.classify_conflict(old, new)
    applied = knowledge.apply_conflict(decision)

    assert decision.old_memory_id == old.memory_id
    assert decision.new_memory_id == new.memory_id
    assert decision.strategy in {"keep_new", "manual_review", "merge"}
    assert applied.memory_id in {old.memory_id, new.memory_id}


def test_retrieval_runtime_is_shared_with_knowledge_adapter() -> None:
    _, _, _, knowledge, retriever = _runtime_services()

    assert retriever.runtime is knowledge.runtime
    assert (
        knowledge.runtime.bm25.__class__.__module__
        == "modules.knowledge_retrieval.algorithm_v1_1.bm25"
    )


def test_dense_success_preserves_vector_ranking_without_bm25_fusion() -> None:
    class Embedding:
        def health(self):
            return {"status": "ok"}

        def encode(self, texts):
            assert texts == ["query"]
            return {"vectors": [[1.0, 0.0]]}

        def model_info(self):
            return {"model_name": "test-dense"}

    class VectorStore:
        def query(self, request):
            assert request["filter_user_id"] == "user-1"
            return [
                {
                    "vector_pk": 1,
                    "score": 0.91,
                    "meta": {"memory_id": "dense-first"},
                },
                {
                    "vector_pk": 2,
                    "score": 0.82,
                    "meta": {"memory_id": "dense-second"},
                },
            ]

    class BM25:
        def search(self, *args, **kwargs):
            raise AssertionError("BM25 must not run when dense retrieval succeeds")

    result = DenseFirstRetrieverV12(Embedding(), VectorStore(), BM25()).search(
        {"query": "query", "user_id": "user-1", "top_k": 2}
    )

    assert [item["memory_id"] for item in result["items"]] == [
        "dense-first",
        "dense-second",
    ]
    assert [item["score"] for item in result["items"]] == [0.91, 0.82]
    assert result["meta"]["degraded"] is False
    assert result["meta"]["retrieval_mode"] == "dense"


def test_bm25_is_used_only_when_dense_provider_fails() -> None:
    class Embedding:
        def health(self):
            return {"status": "ok"}

        def encode(self, texts):
            raise RuntimeError("embedding unavailable")

        def model_info(self):
            return {"model_name": "test-dense"}

    class VectorStore:
        def query(self, request):
            raise AssertionError("vector query must not run after encode failure")

    class BM25:
        def search(self, query, **kwargs):
            assert query == "query"
            return [
                {
                    "doc_id": "sparse-first",
                    "score": 3.2,
                    "meta": {"memory_id": "sparse-first"},
                }
            ]

    result = DenseFirstRetrieverV12(Embedding(), VectorStore(), BM25()).search(
        {"query": "query", "user_id": "user-1", "top_k": 2}
    )

    assert [item["memory_id"] for item in result["items"]] == ["sparse-first"]
    assert result["meta"]["degraded"] is True
    assert result["meta"]["retrieval_mode"] == "bm25_fallback"


def test_no_answer_rule_is_optional_and_dense_only() -> None:
    low_confidence = [{"score": 0.689}, {"score": 0.678}]

    assert not _should_reject_no_answer(
        low_confidence,
        enabled=False,
        degraded=False,
        score_threshold=0.69,
        margin_threshold=0.015,
    )
    assert _should_reject_no_answer(
        low_confidence,
        enabled=True,
        degraded=False,
        score_threshold=0.69,
        margin_threshold=0.015,
    )
    assert not _should_reject_no_answer(
        low_confidence,
        enabled=True,
        degraded=True,
        score_threshold=0.69,
        margin_threshold=0.015,
    )


def test_bm25_state_is_restored_after_runtime_restart(tmp_path) -> None:
    embedding = MockEmbeddingProvider("deterministic-test")
    vector_store = MockVectorStoreAdapter()
    repository = MockMemoryRepository()
    embedding.start()
    vector_store.start(
        VectorStoreConfig(
            provider="memory",
            collection_name="test",
            expected_dimension=8,
        )
    )
    app_config = SimpleNamespace(
        storage=SimpleNamespace(data_dir=tmp_path),
    )
    first = KnowledgeServiceAdapter(
        embedding,
        vector_store,
        app_config=app_config,
    )
    result = first.ingest([_event(text="persistent dark theme")], [])
    _commit(repository, vector_store, result)

    second = KnowledgeServiceAdapter(
        embedding,
        vector_store,
        app_config=app_config,
    )
    retriever = HybridRetrieverAdapter(
        embedding_provider=embedding,
        vector_store=vector_store,
        memory_repository=repository,
        knowledge_service=second,
        config={"candidate_k": 30},
    )

    sparse = second.runtime.bm25.search(
        "persistent dark theme",
        top_k=5,
        filter_user_id="user-1",
    )
    response = retriever.search(
        SearchRequest(
            request_id="search-after-restart",
            user_id="user-1",
            query="persistent dark theme",
            top_k=5,
        )
    )

    assert sparse[0]["doc_id"] == result.records[0].memory_id
    assert response.items[0].memory_id == result.records[0].memory_id


def test_repository_tombstone_prunes_persisted_bm25_candidate(tmp_path) -> None:
    embedding = MockEmbeddingProvider("deterministic-test")
    vector_store = MockVectorStoreAdapter()
    repository = MockMemoryRepository()
    embedding.start()
    vector_store.start(
        VectorStoreConfig(
            provider="memory",
            collection_name="test",
            expected_dimension=8,
        )
    )
    app_config = SimpleNamespace(
        storage=SimpleNamespace(data_dir=tmp_path),
    )
    knowledge = KnowledgeServiceAdapter(
        embedding,
        vector_store,
        app_config=app_config,
    )
    retriever = HybridRetrieverAdapter(
        embedding_provider=embedding,
        vector_store=vector_store,
        memory_repository=repository,
        knowledge_service=knowledge,
        config={"candidate_k": 30},
    )
    result = knowledge.ingest([_event(text="forget persistent theme")], [])
    _commit(repository, vector_store, result)
    memory_id = result.records[0].memory_id
    repository.logical_delete(
        ForgetExecutionPlan(
            request_id="forget-request",
            user_id="user-1",
            plan_id="forget-plan",
            memory_ids=[memory_id],
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
    )

    response = retriever.search(
        SearchRequest(
            request_id="search-after-forget",
            user_id="user-1",
            query="forget persistent theme",
            top_k=5,
        )
    )
    state = json.loads(
        (tmp_path / "bm25_index.json").read_text(encoding="utf-8")
    )

    assert response.items == []
    assert state["documents"] == []
    assert knowledge.runtime.bm25.search("forget persistent theme") == []
