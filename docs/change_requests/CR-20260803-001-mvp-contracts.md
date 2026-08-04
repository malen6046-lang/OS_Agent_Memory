# CR-20260803-001: MVP public contracts

## Control

- Status: Closed
- Baseline: OS Agent Memory Module Interface Plan V1.2.2
- Freeze level: F1
- Proposed by: project maintainer
- Approved by: project maintainer (authorization recorded in the 2026-08-03 development session)
- Approval date: 2026-08-03
- Compatibility: additive contract completion; existing V1.2 field names and enum values remain unchanged

## Current problem

The MVP has working API, database, dependency-container, and orchestration
skeletons, but the planned Schema and Protocol files are empty. Callers are
therefore forced to use local request models, dictionaries, or `Any`, and the
Mock implementations cannot be checked against a frozen interface.

## Approved change

Complete only the public objects required by the current MVP vertical slice:

1. ingestion, preference, knowledge, safety, repository commit, vector sync,
   idempotency, and audit;
2. hybrid search with user/status isolation and degraded fallback metadata;
3. two-stage forget preview and execution;
4. evaluation-run submission;
5. embedding/vector provider lifecycle;
6. one success/error response envelope used by API and orchestration.

## Frozen decisions

### Dependency direction

The only cross-module chain is:

`API -> Orchestrator -> contracts.Protocol -> implementation`.

Orchestrator must not import FastAPI routers, database implementations, Kylin
SDK types, adapters, repositories, or algorithm implementations.

### Synchronization

Protocol methods are synchronous, matching V1.2.1. The asynchronous
Orchestrator owns thread offloading and request timeout handling. Mock and Real
implementations must keep the same synchronous signatures.

### Ingestion transaction boundary

- `IdempotencyRepository` checks and records request replay state.
- Preference, safety, and knowledge services produce contract objects.
- `MemoryRepository.commit_ingest()` commits structured records.
- `VectorStoreAdapter.upsert()` synchronizes committed vector items.
- `AuditRepository.record()` records operation metadata without sensitive body.

### Forget transaction boundary

- `ForgetService.preview()` returns candidates and a confirmation token.
- `ForgetService.execute()` validates the token and returns an execution plan;
  it does not mutate storage.
- `MemoryRepository.logical_delete()` performs tombstone changes.
- Orchestrator then performs precise vector deletion and audit in that order.

### Evaluation

`EvaluationService.run()` returns an accepted/running/completed/failed run
record. Real execution may be asynchronous behind the Protocol.

### Response and errors

All responses contain `success`, `request_id`, `data`, `error`, and `meta`.
`meta` contains elapsed time and degraded status. Error codes are append-only;
the MVP freezes the codes already named by V1.2.1 plus
`DEPENDENCY_UNAVAILABLE` and `INTERNAL_ERROR` from the V1.2.2 domains.

## Files in scope

- `contracts/schemas/`: knowledge, retrieval, forget, evaluation, provider,
  responses, and additive persistence/safety schemas
- `contracts/protocols/`: preference, knowledge, retrieval, forget, safety,
  embedding, vector_store, memory, and evaluation
- contract tests and contract changelog
- Mock implementations, dependency assembly, Orchestrator binding, and unified
  API response adapter required to consume the contracts

## Non-goals

- no Kylin SDK integration;
- no algorithm implementation or ranking changes;
- no database migration or storage-format change;
- no rename, deletion, or semantic change to existing Envelope, MemoryRecord,
  PreferenceRecord, or existing enum members;
- no frontend implementation.

## Verification

```text
pytest tests/contract -v
pytest tests/unit/orchestrator -v
pytest tests/unit/dependencies -v
pytest tests/integration -v
```

## Rollback

Revert the CR implementation commit as one unit. This CR does not migrate or
delete stored data and does not enable a real provider by default.

## Closure

- Implementation commit: working tree pending maintainer commit
- Test evidence: `pytest -q` -> 153 passed in 2.45s on CPython 3.12.7
- Remaining dependencies: real repository/algorithm/Kylin implementations and
  frontend are outside this CR
- Closure decision: accepted and closed under the project maintainer's delegated
  approval; ready for project-maintainer commit
