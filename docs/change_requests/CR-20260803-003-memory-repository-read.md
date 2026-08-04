# CR-20260803-003: User-scoped MemoryRepository reads

## Control

- Status: Closed
- Baseline: OS Agent Memory Module Interface Plan V1.2.2
- Freeze level: F1 Protocol; F2 integration flow
- Proposed and approved by: project maintainer
- Approval date: 2026-08-03
- Compatibility: additive synchronous method; no existing signature changes

## Problem

The frozen `MemoryRepository` can commit and tombstone records but cannot read
records back. A retriever can obtain vector hit IDs, but it cannot hydrate those
IDs into frozen `MemoryRecord` objects without importing a concrete database
implementation. That would violate the required dependency direction and
prevents a real API import-search-forget demonstration.

## Approved change

Add one synchronous method:

```python
get_by_ids(
    user_id: str,
    memory_ids: list[str],
    statuses: list[MemoryStatus] | None = None,
) -> list[MemoryRecord]
```

The method must enforce `user_id`, preserve requested ID order, optionally
filter by status, and never return another user's record. Mock and SQLite
implementations are updated in the same change.

## Demo implementation

- Mock knowledge creates deterministic contract records from events.
- Mock vector storage retains only application-lifetime test data.
- Mock retrieval embeds the query, requests user/status-filtered vector hits,
  and hydrates records through `MemoryRepository.get_by_ids()`.
- Forget tombstones the record, deletes the exact vector key, and subsequent
  search no longer returns it.

This is deterministic test/demo behavior, not the production ranking algorithm.

## Non-goals

- no Kylin SDK or real vector-engine integration;
- no production retrieval/ranking algorithm;
- no changes to existing Schema fields, enums, API paths, or error codes;
- no direct API or Orchestrator dependency on Repository implementations.

## Verification

```text
pytest tests/contract -v
pytest tests/unit/persistence -v
pytest tests/unit/dependencies -v
pytest tests/integration/api -v
pytest tests/integration -v
pytest -q
```

## Rollback

Revert this CR as one unit. Existing persisted SQLite rows require no migration
or rollback because the change only adds read behavior.

## Closure

- Implementation commit: working tree pending project-maintainer commit
- Test environment: CPython 3.12.7, SQLite, deterministic Mock providers
- Test evidence: contract 94 passed; persistence 9 passed; dependencies 9
  passed; API 11 passed; integration 16 passed; full suite 165 passed in
  3.68s; `python -m app.main` exited 0
- Remaining target validation: real algorithm, persistent vector adapter, and
  Kylin Linux Desktop V11
- Closure decision: accepted and closed under delegated project-maintainer
  approval; ready for commit
