# Algorithm V1.1 knowledge/retrieval adapter

This package is the frozen-contract boundary for the pinned donor sources in
`modules/knowledge_retrieval/algorithm_v1_1`.

The backend calls `KnowledgeServiceAdapter` and `HybridRetrieverAdapter`, never
the donor `async_adapter.py` or `service_factory.py`. The donor
`KnowledgeService.ingest()` is also excluded because it writes metadata,
BM25, and vectors before the backend repository transaction. The adapter
instead creates frozen `MemoryRecord` objects, reuses the donor BM25,
conflict classifier, and hybrid retriever, and lets the existing Orchestrator
own repository/vector/audit side effects.

Search candidates are always hydrated through `MemoryRepository.get_by_ids`
with the requesting user and `active` status. Vector or BM25 metadata is never
treated as authoritative. Raw embedding vectors remain internal to persistence
and vector operations and are removed from public search-result attributes.

The BM25 index is rebuilt at startup from a minimal JSON state file in the
configured storage directory (`bm25_index.json`). The state contains only
BM25 document fields, never embedding vectors. Set `OS_AGENT_BM25_STATE` to
override its location. The index is updated while the knowledge adapter builds
records and may contain a stale candidate if the later repository commit
fails; repository hydration prevents such candidates from escaping and prunes
them from both the live BM25 index and the persisted state.
