# CR-20260803-002: Configured SQLite repositories in Mock service mode

## Control

- Status: Closed
- Baseline: OS Agent Memory Module Interface Plan V1.2.2
- Freeze level: F1 configuration semantics; F3 repository implementation
- Proposed and approved by: project maintainer
- Approval date: 2026-08-03
- Compatibility: existing configurations without implementation paths keep the
  same deterministic Mock repositories

## Problem

The binary `services.mode` switch requires every algorithm and persistence
implementation to become real at the same time. That blocks the MVP from using
SQLite persistence while the algorithm modules are still under parallel
development.

## Approved change

When `services.mode` is `mock`, an explicitly configured repository
implementation path selects that implementation for Memory, Idempotency, or
Audit persistence. An omitted path continues to select the corresponding Mock.
An invalid explicit path fails startup and never silently falls back.

`development.yaml` explicitly selects the SQLite implementations. The default
profile remains fully Mock and deterministic.

## Boundaries

- no Schema or Protocol change;
- no algorithm or Kylin implementation;
- no API or Orchestrator flow change;
- no request body is stored in audit records;
- SQLite repositories remain behind the frozen Repository Protocols.

## Verification

```text
pytest tests/unit/database -v
pytest tests/unit/persistence -v
pytest tests/unit/dependencies -v
pytest tests/integration -v
pytest -q
```

## Rollback

Remove the three implementation paths from `development.yaml` or revert this
change. The default profile is unaffected.

## Closure

- Implementation commit: working tree pending project-maintainer commit
- Test environment: CPython 3.12.7, SQLite, Windows development host
- Test evidence: database 9 passed; persistence 8 passed; dependencies 9
  passed; orchestrator 17 passed; integration 15 passed; full suite 163 passed
  in 4.29s; `python -m app.main` exited 0
- Remaining target validation: Kylin Linux Desktop V11 and real vector engine
- Closure decision: accepted and closed under delegated project-maintainer
  approval; ready for commit
