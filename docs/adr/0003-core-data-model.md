# 0003. Core data model and the indexed-values container

- Status: Accepted
- Date: 2026-11-24
- Related: `docs/specs/00-domain-model.md` §2–4, OQ-1, OQ-6, OQ-24, OQ-25

## Context

The unit of analysis is `spatial unit × social group × service × time` (Paper 4 §3). Many quantities omit some of these dimensions (for example `SS_{i,g,s}` has no time; `DemandRate^g` has only group and service) or add others (facility, mode, scenario, Monte Carlo sample, discrete state). Outputs must carry uncertainty (AGENTS.md invariant 6). Quantities of different services must never be summed (OQ-24), and groups may overlap (OQ-6).

We need (a) immutable typed entities and (b) one container for indexed values that every module can share.

## Options for the container

1. **xarray `DataArray`** (Apache-2.0): named dimensions and labelled coordinates, broadcasting by name, NumPy-backed, optional Dask/Zarr/NetCDF, interoperates with pandas. Adds xarray + pandas as dependencies.
2. **pandas `DataFrame` with a MultiIndex**: familiar, good I/O, but sparse long format, no named broadcasting, and easy to mis-align.
3. **Typed wrapper over plain NumPy** with our own dimension metadata: no extra dependency, but we would reimplement labelled selection, alignment and I/O.

## Decision

- Entities are frozen `dataclasses` with validation in `__post_init__` (no Pydantic in `core`, to keep it light and framework-free).
- Indexed values use **`IndexedValues`, a thin immutable wrapper over `xarray.DataArray`** (`core/src/solidaritynode_core/model/indexed.py`):
  - only dimensions from the `Dim` enum are allowed (`unit`, `facility`, `group`, `service`, `mode`, `scenario`, `time`, `state`, `sample`), named after the OQ-1 notation; any subset may be present, so absent dimensions are natural;
  - coordinate labels must be unique; values are copied and read-only;
  - `check_aligned` refuses mismatched shared dimensions;
  - `sum_over(SERVICE)` is refused (OQ-24) and `sum_over(GROUP)` is refused while overlap handling is open (OQ-6);
  - `to_dataarray()` gives a copy for library interop.
- Uncertain scalars are `PointValue | Samples | DiscreteDistribution`; arrays carry uncertainty in a `sample` or `state` dimension.
- `ServiceQuantity` carries service, service unit and reference period; adding quantities that differ in any of them raises `UnitMismatchError` (OQ-24, OQ-25).
- Geometry is typed as any object with `__geo_interface__`, so `core` needs no geometry library yet (GeoPandas/Shapely arrive with the accessibility module).
- Scenarios are overlays on the baseline (Spec 00 §3). Besides disruption severities, network disruption, rationing case and reference level, `Scenario.interventions` holds typed what-if placeholders (`CapacityChange`, absolute or relative; `NewFacility`; Paper 1 §13) with **no behaviour**. The JSON schema and versioning of stored scenarios are ADR 0016.
- A variable catalogue (`model/catalogue.py`) mirrors Spec 00 §4 and records each variable's kind (BN node, computed, parameter, output…) and dimensions, so tests can keep these categories distinct.

## Consequences

- `core` depends on `numpy` and `xarray` (and transitively `pandas`, `packaging`); all BSD/Apache licensed.
- The wrapper hides most of xarray's API on purpose; modules that need more can use `to_dataarray()` internally and wrap the result again.
- Storage of large arrays (Parquet vs Zarr/NetCDF) is a separate decision (ADR 0008).
- If performance or typing becomes an issue, the wrapper keeps the public API stable while the backend changes.

## Demo data in the database (temporary)

The synthetic demo dataset (`data/synthetic/demo/`, DP-001) is loaded by `make seed` into a separate PostgreSQL schema **`demo`** (Alembic migration `0002`), never into `public`. Its tables mirror the demo files, not this data model, and exist only so tests and UAT can inspect realistic-looking data. **The `demo` schema is temporary and will be replaced by data-package import in the platform PR** (ADR 0013). The loader copies data and computes nothing.
