# Algorithm V1.1 preference/safety adapters

These synchronous adapters are the only production-facing entry points for
the pinned sources in `modules/preference_safety/algorithm_v1_1`.

- Preference converts `Envelope` and frozen preference models to the donor
  dictionary surface, partitions state by user/scope, and preserves the
  donor rule behavior (including case sensitivity and positive polarity).
- Safety calls the donor text detector and returns only reason/entity types;
  values, masks, and offsets never cross the frozen boundary.
- Forget calls only donor `preview()` for instruction parsing and risk
  heuristics. Adapter `execute()` validates a process-local confirmation
  plan and returns `ForgetExecutionPlan`; repository, vector, and audit
  mutations remain in the Orchestrator. Donor `execute()` is never called.

The default and development profiles remain Mock. Use
`OS_AGENT_ENV=preference_safety` for this module alone or
`OS_AGENT_ENV=algorithm_modules` for both algorithm modules.
