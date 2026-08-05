from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.dependencies.mock_services import (
    MockEmbeddingProvider,
    MockMemoryRepository,
    MockVectorStoreAdapter,
)
from adapters.knowledge_retrieval.knowledge import KnowledgeServiceAdapter
from adapters.knowledge_retrieval.retrieval import HybridRetrieverAdapter
from contracts.schemas.common import MemoryStatus
from contracts.schemas.envelope import Envelope
from contracts.schemas.persistence import IngestServiceResult
from contracts.schemas.provider import VectorStoreConfig
from contracts.schemas.retrieval import SearchRequest
from modules.knowledge_retrieval.algorithm_v1_1.knowledge_service import (
    KnowledgeService as LegacyKnowledgeService,
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
