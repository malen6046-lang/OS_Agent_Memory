# preference_safety implementations

`algorithm_v1_1/` is the immutable source snapshot from
`Algorithm---V1.1` commit `8c1e47d`. The `preference_safety` and
`algorithm_modules` profiles call that snapshot only through
`adapters/preference_safety/`.

V1.2 modules outside the donor provide canonical preference keys, semantic
signal extraction, separator-resistant safety detection, and conservative
forget intent parsing. The staged adapters select these V1.2 enhancements
while retaining explicit legacy-injection paths for compatibility tests.

Preference state and forget confirmation plans remain process-local. Run
the staged profiles with one application worker until durable state is
implemented.
