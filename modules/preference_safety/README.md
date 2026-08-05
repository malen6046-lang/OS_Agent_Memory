# preference_safety integration slice

This package adapts the rule and parsing behavior from
`Algorithm---V1.1` commit `8c1e47d` to the frozen V1.2.2 synchronous
Protocols.

Implemented boundaries:

- `PreferenceService`: rule extraction, idempotent in-memory merge, scoped
  resolution, and immutable revision history.
- `SafetyService`: Envelope payload scanning with non-sensitive contract
  results.
- `ForgetService`: preview and confirmation validation only. Database
  tombstoning, vector deletion, and audit remain owned by the Orchestrator.

Enable this staged slice with `OS_AGENT_ENV=preference_safety`. The default
and development profiles continue to use Mock algorithm services.
The staged graph still reports `mock: true` because knowledge, retrieval,
providers, repositories, and evaluation have not been cut over yet.

Preference state and forget confirmation plans are process-local in this
stage. Preference persistence cannot be connected safely until the ingest
unit of work supplies the backing `memory_id` before the preference foreign
key is written.

Run this staged profile with one application worker. Multiple workers do not
share preference state or confirmation plans; durable cross-worker state is
part of the later persistence/cutover slice.
