# 0016. Scenario schema and versioning

- Status: Proposed (stub, needs a human decision)
- Date: 2026-11-24
- Related: Spec 00 §3 (Scenario), Paper 1 §13, Paper 3 §7–10, OQ-16, OQ-24; ADR 0003, 0013, 0017

## Context

Spec 00 §3: a scenario is a set of **changes relative to the baseline** (an overlay, never a copy of the data): what-if interventions (Paper 1 §13, for example capacity +20 %, new facility) and disruptions (Paper 3: facility severities `DS ∈ [0,1]`, closed network edges), plus a rationing case (OQ-24) and a reference-scenario flag (OQ-16). Scenarios are **stored as versioned, schema-validated JSON with an owner and visibility** (private, shared). `core.model.Scenario` already holds the typed form, with `CapacityChange` and `NewFacility` as placeholders without behaviour.

The demo scenario `data/synthetic/demo/scenarios/C-DEMO-REF.json` uses a draft layout (`schema: "solidaritynode-scenario/0.1-draft"`): `id`, `version`, `name`, `kind`, `description`, `facility_severities`, `network_disruption` (`modes`, `affected_link_ids`), `interventions`, `rationing`, `reference_level`. This is not a decision.

## Options to evaluate

1. **JSON Schema** published in the repo, generated from Pydantic models in the backend and mapped to `core.model.Scenario`.
2. Pydantic models only (schema implied by code).
3. YAML for authoring, JSON for storage.

## Questions to answer before deciding

- Versioning: is every edit a new immutable version (needed for run reproducibility, ADR 0017)? How are versions numbered?
- How does a scenario refer to features: stable ids from the data package (ADR 0013)? What happens when a referenced feature is closed in a newer package?
- Schema evolution and migration of stored scenarios.
- How the OQ-16 reference scenarios (minor, moderate, severe) are constructed: open, not part of this ADR.
- Whether interventions and disruptions may be combined in one scenario (the spec does not say).

## Decision

Not decided.

## Consequences

To be written.
