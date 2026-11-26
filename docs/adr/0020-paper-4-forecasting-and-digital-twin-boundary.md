# 0020. Boundary between Paper 4 forecasting and a future digital twin

- Status: Proposed (stub, needs a human decision)
- Date: 2026-11-26
- Deciders:
- Related: AGENTS.md invariant 8, OQ-23, OQ-31, OQ-32, OQ-33, OQ-34, OQ-40; ADR 0006, 0017

## Context

AGENTS.md invariant 8: **the Digital Twin (ψηφιακό δίδυμο) is a future direction, not an
assumption; do not build twin-specific machinery yet.** OQ-23 keeps the wording consistent
(Paper 1's conclusion speaks of a "probabilistic baseline Digital Twin").

The maintainer decided (2026-11-26) that Paper 4 includes **forecasting and (near) real-time
maps** (OQ-31 to OQ-34): a current picture, a nowcast by DBN filtering and a forecast by DBN
prediction with external signals; risk maps from hazard forecasts; a weekly and an hourly time
scale with a hand-over between them; one-month and conditional forecasts. Each update is a
**scheduled, reproducible run** in the worker, not a continuous stream, and forecasts support
decisions without acting automatically (invariant 7).

These features come close to what is often called a digital twin, so the line must be stated
before Paper 4 is specified, or tickets will drift into twin machinery.

## Questions to answer

- Which of the following are **inside Paper 4** and which **stay for later**:
  - scheduled nowcast and forecast runs at fixed intervals (decided inside: OQ-31);
  - ingestion of external hazard forecasts and warnings (OQ-40);
  - automatic start of crisis mode by a warning (OQ-31 says "by a warning or by hand");
  - continuous streaming updates, event-driven state synchronisation, bidirectional coupling
    with operational systems, automatic actions (OQ-31 rejects streaming and automatic action);
  - a persistent "live" state of the territory kept between runs, as opposed to state
    reconstructed by each run from recorded observations.
- How the wording of Papers 1 and 4 refers to the digital twin (OQ-23).
- Which platform pieces these need (scheduled jobs: ADR 0006 trigger 3; result retention for
  frequent crisis runs: ADR 0017), and what must **not** be built yet.

## Options

1. **Forecasting as scheduled runs only** (the OQ-31 decision): every map is a normal run with
   recorded inputs; no persistent live state, no streaming, no actions. A digital twin, if ever,
   is a separate future ADR.
2. **Option 1 plus a persistent nowcast state** carried between runs, still without streaming
   or actions.
3. **Treat Paper 4 as a first digital twin** (live state, streaming inputs): contradicts
   invariant 8 and OQ-31 as decided.

## Decision

Not decided. To be taken by the maintainer before the Paper 4 spec (`04-resilience.md`) is
written.

## Consequences

To be written with the decision: which Paper 4 tickets are allowed, what is explicitly out of
scope, and what would make us revisit invariant 8.
