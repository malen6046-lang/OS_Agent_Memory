# knowledge_retrieval implementations

`algorithm_v1_1/` is the immutable source snapshot from
`Algorithm---V1.1` commit `8c1e47d`. It contains the donor BM25, conflict,
hybrid retrieval, knowledge service, and memory-tier implementations.

The frozen backend does not call the donor `service_factory.py`, async
adapter, or storage-writing `KnowledgeService.ingest()` entry directly.
`adapters/knowledge_retrieval/` owns the V1.2.2 DTO conversion, repository
hydration, user/status isolation, and provider shape bridges.

The older files at this directory root remain for branch history and their
original unit tests; the `algorithm_modules` profile selects only the
versioned snapshot through the contract adapters.
