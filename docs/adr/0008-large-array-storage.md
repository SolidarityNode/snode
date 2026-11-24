# 0008. Storage of large arrays (Parquet)

- Status: Accepted for v0.1, to be revisited
- Date: 2026-11-24 (accepted for v0.1: 2026-11-25)
- Related: AGENTS.md "Large datasets live in files (Parquet)"; ADR 0003

## Context

Results are indexed by `unit × group × service × time` plus scenario and Monte Carlo sample, and can be large. AGENTS.md states that large datasets live in Parquet files with metadata and result indexes in PostgreSQL/PostGIS. `core` represents arrays as `IndexedValues` (xarray, ADR 0003).

## Options to evaluate

1. **Parquet** in long format (one row per cell and sample) via PyArrow (Apache-2.0) or Polars (MIT); GeoParquet for geometries.
2. **Zarr** or **NetCDF** for dense labelled arrays (native for xarray).
3. Both: Parquet for tabular inputs, Zarr for dense result cubes.

## Questions to answer before deciding

- Where do files live (local volume, S3-compatible object storage) and how are they referenced from the database index?
- Partitioning (by run, scenario, service) and retention.
- Does storing per-sample results raise privacy concerns when units are small (OQ-21)?
- Should `core` own the I/O, or the backend (keeping `core` free of storage concerns)?

## Decision

**Accepted for v0.1, to be revisited: option 1, Parquet in long format via PyArrow**
(Apache-2.0), written by the **backend** (`core` stays free of I/O).

- Per-sample values: `<results_dir>/runs/<run_id>/samples.parquet`, columns `unit_id, group_id,
  service_id, time_label, indicator, sample, value`; `results_dir` is the `results` volume
  (`/data/results` in compose). The run row stores the path.
- Summary values per `unit × group × service × time` (central value and interval) in table
  `run_results`; model tables (`travel_times`, `unit_changes`) as JSON in `run_tables`.
- Files are written to a temporary name and renamed, so a crash never leaves a partial file
  referenced by a run.

## Consequences

- No retention or partitioning yet; one file per run. Revisit with object storage or Zarr when
  Monte Carlo sample counts grow.
- Per-sample files of small units may raise OQ-21 questions once real operational data exist.
