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
- **Sample semantics.** `sample` identifies one **joint Monte Carlo draw** shared by all cells of
  a run: draw *i* uses the same values of every shared uncertain parameter across units, groups
  and services. Models must sample jointly, never independently per cell, so totals computed
  sample by sample (ADR 0017, `summarise_total`) have correct intervals. This is part of the
  model registry contract (`CellSamples`, `ModelResult`, which also requires every cell to have
  the same number of draws). `diagnostic-v0` complies since version **0.2.0**: draw *i* has one
  shared factor plus an independent term per cell (each cell standard normal, correlation 0.5
  between cells); 0.1.0 drew every cell independently. Core test
  `test_samples_are_joint_draws_so_totals_across_units_use_the_same_index`.
- **Layout** (results schema version 1): id columns dictionary-encoded; `value` stored as
  `float32` unless the model declares `float64` (`ModelSpec.sample_dtype`), and the summary
  statistics are computed from the values at that precision, so they can be reproduced exactly
  from the file; `sample` as `int32`; rows sorted by indicator, unit, group, service, time and
  sample; zstd compression.
- **Metadata and integrity.** The Parquet key-value metadata (`solidaritynode.*`) records the run
  id, model id and version, data package id and version, data version id, results schema
  version, value precision and sort order. The file's SHA-256 is stored on the run row
  (`runs.samples_sha256`, shown under Reproducibility and in `metadata.json`) and verified on
  every read (`services.samples.read_samples`) and export: a missing, changed or foreign file is
  refused (export answers 409). Runs stored before migration 0006 have no checksum and are not
  checked.
- **Size estimate.** Before a run starts, its samples file size is estimated from the run
  configuration and the data version: draws × core units × groups × services × sampled
  indicators × 28 bytes (float32; an upper bound before compression). Above
  `SOLIDARITYNODE_SAMPLES_WARN_MB` (default 500) the backend logs a warning and the run page
  shows one; the run is still queued. The estimate and the limit are stored on the run.
- Summary values per `unit × group × service × time` (mean, median and interval quantiles, ADR 0017) in table
  `run_results`; model tables (`travel_times`, `unit_changes`) as JSON in `run_tables`.
- Files are written to a temporary name and renamed, so a crash never leaves a partial file
  referenced by a run.

## Consequences

- No retention or partitioning yet; one file per run. Revisit with object storage or Zarr when
  Monte Carlo sample counts grow.
- **Back up results together with the database.** The run row points to its samples file and
  records its checksum; a database backup without the `results` volume (or the reverse) leaves
  runs whose samples cannot be read or verified. Back up both at the same point in time and
  restore them together.
- **OQ-21 (clarification, the question stays open).** Model samples are **estimates** produced
  by a model from aggregate inputs, not records of people. The privacy limits of OQ-21 (minimum
  cell sizes, aggregation, retention) apply mainly to quantities derived from **tickets**
  (Paper 4: observed requests, take-up, consequences), and to any model output that reproduces
  them at a fine level. Revisit when ticket-derived quantities enter a model.
