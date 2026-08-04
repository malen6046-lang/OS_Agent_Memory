## 1.2.2 - 2026-08-03

- Approved and implemented CR-20260803-003 adding user-scoped
  `MemoryRepository.get_by_ids()`
  for retrieval hydration; existing methods and data schemas are unchanged.
- Approved and implemented CR-20260803-001 for the MVP public contracts.
- Added the planned knowledge, retrieval, forget, provider, evaluation, and
  unified response schemas.
- Added additive safety and persistence command/result schemas.
- Added synchronous Preference, Knowledge, Retrieval, Forget, Safety,
  Embedding, VectorStore, Memory Repository, Audit, Idempotency, and Evaluation
  Protocols.
- Added `PreferenceCandidate` without changing existing `PreferenceRecord`
  fields.
- Preserved all existing Envelope, MemoryRecord, PreferenceRecord, common enum,
  and contract-version semantics.
