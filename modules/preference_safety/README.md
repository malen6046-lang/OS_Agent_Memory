# preference_safety implementations

`algorithm_v1_1/` is the immutable source snapshot from
`Algorithm---V1.1` commit `8c1e47d`. The `preference_safety` and
`algorithm_modules` profiles call that snapshot only through
`adapters/preference_safety/`.

The contract-native service files at this directory root were produced by
the earlier `d3fe10e` integration and include additional policies such as
last-mentioned preference resolution, negation polarity, stricter safety
rules, and hardened forget-plan handling. They are retained as a vNext
implementation for review, but neither adapter profile selects them.

Preference state and forget confirmation plans remain process-local. Run
the staged profiles with one application worker until durable state is
implemented.
