# AGENTS.md (core)

Applies to files under core/, in addition to the root AGENTS.md. If the two conflict, the root wins; report the conflict.

Explanations and examples: [docs/conventions/core.md](../docs/conventions/core.md).

## Rules

- Implement only what a spec states. Every public function cites its spec section, and `OQ-n` where relevant.
- No web frameworks, database drivers or file-system side effects in model code. I/O lives at the edges.
- Randomness only through an explicit `numpy.random.Generator` or seed argument.
- Quantities carry their service unit and reference period. Never add quantities of different services or periods.
- Every algorithm has a known-answer test on the synthetic demo data.
- Bump model ids and versions whenever outputs can change.
