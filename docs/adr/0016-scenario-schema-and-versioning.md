# 0016. Scenario schema and versioning

- Status: Accepted for v0.1, to be revisited
- Date: 2026-11-24 (accepted for v0.1: 2026-11-25)
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

**Accepted for v0.1, to be revisited: option 1, a Pydantic model with a published JSON Schema.**

- `ScenarioBody` (`schema_version: "1.0"`): `capacity_changes` (facility, service, input
  `places | staff | throughput`, `absolute | relative` percent, amount), `new_facilities` (id,
  name, type, an existing network `node_id`, services with capacity inputs), `severities`
  (`DS ∈ [0, 1]` per facility), `closed_edges` (`edge_ids` and `modes`), `rationing`
  (`uniform | concentrated`, required for disruption scenarios, OQ-24) and `reference_level`
  (the reference-scenario flag; construction of reference scenarios stays open, OQ-16). Unknown
  fields are refused. It maps to `core.model.Scenario` (`NewFacility` gains `node_id`).
- **Intervention placeholders** (Paper 1 §13, §15.7), added without a schema version change
  because no scenario has been stored outside development (`schema_version` stays `1.0`; the new
  fields default to empty, so stored versions stay valid):
  - `network_changes.edge_changes`: travel time or speed of one existing edge for one mode,
    `absolute` (minutes or km/h) or `relative` (percent, above −100 %);
  - `network_changes.new_edges`: a new edge between two existing nodes, with a travel time per
    mode and a `closable` flag;
  - `population_changes`: one unit and group, `absolute` (persons) or `relative` (percent).
  They map to `core.model.EdgeChange`, `NewEdge` and `PopulationChange`, are validated (schema
  rules, duplicates, references against the data version, no negative results where the
  baseline is known) and **recorded only**: runs list them under `recorded_only` (shown on the
  run page as "Recorded, no effect yet"), nothing is applied yet. The editor keeps them when
  saving and says they have no effect yet. Travel times and speeds must stay **strictly
  positive** (relative changes above −100 %, absolute travel-time changes leaving more than
  0 minutes, new-edge times > 0): **closing a road uses `closed_edges`**, never a change to zero.
  A new edge that the same scenario also closes is reported on the run ("added, then closed,
  so no net effect", OQ-30), never ignored silently.
- **Order of application** (OQ-30, *proposed default*, recorded in `core.scenarios.overlay` and
  `core.model.Scenario`): interventions first (new facilities, capacity, network, population),
  then disruptions (severities, closed edges), which may also hit the new facilities and new
  edges of the same scenario. This touches the method and must be confirmed when the Paper 3
  spec is written.
- The JSON Schema is exported to `docs/schemas/scenario.schema.json` (`make schemas`); a test
  keeps it current.
- Scenarios refer to features by **stable ids** from the data package. Name, description and
  visibility (`private | shared`) belong to the scenario; every edit creates a new **immutable
  numbered version** (1, 2, …) that records the data version it was created against. Runs refer
  to versions, so old versions stay readable.
- When a newer package closes or lacks a referenced feature, the scenario is **reported** (list,
  editor, import outcome) and cannot be run on that version until edited; nothing is dropped.
- Delete is soft; a hard delete is refused when runs exist. Interventions and disruptions may be
  combined (the spec does not forbid it).

Maintainer decision (2026-11-25, PR #6): the optional `core.model.NewFacility.node_id` (the
existing network node where a new facility is placed) is accepted.

**Why:** one source of truth for validation in the backend; the published schema lets the hub and
other tools check scenarios.

## Consequences

- A schema 2.0 will need a migration of stored versions.
- Severities are recorded and reported only: how DS changes capacity is Paper 3 and not
  implemented. The same holds for edge, new-edge and population changes (Paper 1 §5, §6).
- **Open for later versions of the schema:**
  - **uncertain scenario parameters**, for example DS as a range or distribution sampled in
    the Monte Carlo runs instead of a single value;
  - **time-varying disruptions** for Paper 4 (severities and closures that change over time),
    likely schema 2.0;
  - **per-service severity** (a facility disrupted for one service and not another);
  - **scenario families** for sensitivity analysis and for the OQ-16 reference scenarios
    (minor, moderate, severe), generated from one definition instead of edited one by one.
