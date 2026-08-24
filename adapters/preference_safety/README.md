# Algorithm preference/safety adapters

These synchronous adapters are the only production-facing entry points for
the pinned sources in `modules/preference_safety/algorithm_v1_1`.

- Preference layers V1.2 semantic signals and canonical keys over the frozen
  donor rules, then partitions state by user and scope.
- Safety uses the contract-native V1.2 detector by default and returns only
  reason/entity types; values, masks, and offsets never cross the boundary.
- Forget separates delete and keep clauses, rejects ambiguous candidates, and
  enumerates repository-confirmed active records for bounded or full `all`
  requests. Adapter `execute()` validates a process-local confirmation plan;
  repository, vector, and audit mutations remain in the Orchestrator.

Confirmation plans are still process-local. Durable multi-worker execution
requires a project-owned plan-store/DI change request.

The default and development profiles remain Mock. Use
`OS_AGENT_ENV=preference_safety` for this module alone or
`OS_AGENT_ENV=algorithm_modules` for both algorithm modules.
