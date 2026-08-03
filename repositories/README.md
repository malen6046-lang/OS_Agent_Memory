# SQLite repositories

This package implements the frozen `MemoryRepository`,
`IdempotencyRepository`, and `AuditRepository` Protocols with SQLAlchemy 2.0
and SQLite.

## Configuration

The default profile keeps deterministic in-memory Mock repositories. The
development profile selects these implementations through the existing
`services.*_repository_implementation` paths:

```text
OS_AGENT_ENV=development
```

An explicitly configured implementation that cannot be imported fails startup;
the container does not silently fall back to a Mock.

## Persistence behavior

- Memory records keep searchable columns plus the complete validated contract
  JSON.
- Each `memory_id` receives a stable, collision-checked signed 63-bit
  `vector_pk`.
- `get_by_ids()` hydrates records in requested ID order while enforcing user
  and optional status filters.
- An optional validated vector is read from `attributes.embedding`; missing
  vectors are not fabricated.
- Forget performs a user-scoped tombstone update, increments the revision, and
  returns only the exact vector keys that must be deleted.
- Idempotency records store the fingerprint and response needed for replay.
- Audit records store structured operation metadata, not request bodies.

## Database initialization and migration

`app.core.database.init_db()` creates new tables and adds the repository payload
columns to databases created from migration `0001`. The equivalent SQL is in
`migrations/versions/0002_repository_payloads.sql`.

## Tests

```text
pytest tests/unit/database -v
pytest tests/unit/persistence -v
pytest tests/integration/test_sqlite_orchestration.py -v
```

## Current limitation

Embedding generation remains the responsibility of an injected service or
adapter. These repositories only persist and forward vectors already supplied
through the contract record attributes.
