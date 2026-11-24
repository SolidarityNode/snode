# 0008. Storage of large arrays (Parquet)

- Status: Proposed (stub, needs a human decision)
- Date: 2026-11-24
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

Not decided.

## Consequences

To be written with the decision.
