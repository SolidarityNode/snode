# Core conventions

Rules: [`core/AGENTS.md`](../../core/AGENTS.md). The root [`AGENTS.md`](../../AGENTS.md) also applies.

## Implement only what a spec states

Every public function cites its spec section, and `OQ-n` where relevant.

**Why:** the papers and `docs/specs/` are the source of truth; open questions are decided by the maintainers, not in code.

**Example:** a docstring line such as `Spec 00 §4; OQ-8.` Where an open question blocks the behaviour, raise `NotImplementedError` and cite it.

## No web frameworks, database drivers or file-system side effects in model code

I/O lives at the edges (loaders and writers), not in model functions.

**Why:** `core` must stay a pure, testable library usable from the backend, notebooks and tests. Imports of web frameworks and drivers are already blocked by `tests/test_package.py` and the ruff banned-api rule; file-system side effects are checked in review.

## Explicit randomness

Randomness only through an explicit `numpy.random.Generator` or seed argument.

**Why:** runs must be reproducible from their recorded seed (ADR 0017).

**Example:** `def sample(..., rng: numpy.random.Generator)`, never `numpy.random.random()`.

## Units and reference periods

Quantities carry their service unit and reference period. Never add quantities of different services or periods.

**Why:** a visit, a bed-day and a home-care hour are not comparable (OQ-24); summing them gives a meaningless number.

## Known-answer tests

Every algorithm has a known-answer test on the synthetic demo data (`data/synthetic/demo/`, DP-001).

**Why:** a hand-checked expected value catches errors that property tests and type checks miss.

## Model ids and versions

Bump model ids and versions whenever outputs can change.

**Why:** runs record the model version (ADR 0017); an unchanged version with different outputs breaks reproducibility.
