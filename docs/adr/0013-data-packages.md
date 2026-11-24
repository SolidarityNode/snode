# 0013. Data packages: format, versioning, checksums and buffer

- Status: Proposed (stub, needs a human decision)
- Date: 2026-11-24
- Related: Spec 00 §3 (Data package, Study area, Onboarding, Stable identifiers), OQ-28; ADR 0003, 0008, 0009, 0012; `docs/data-processing/README.md` rule 9

## Context

Spec 00 §3: a data package is a **versioned (semantic versioning), checksummed** bundle for one study area **plus a buffer** of neighbouring units (OQ-28), with layer coverage, changelog and provenance, produced by the hub and imported by an installation after a preview of changes. Features keep stable ids and carry `municipality_id`, `role` (core | buffer), `quality`, `valid_from` / `valid_to`. Each package's `manifest.json` lists the `DP-NNN` processing notes behind its data (`docs/data-processing/README.md`, rule 9).

## Draft manifest format (used by the demo dataset; not yet a decision)

`data/synthetic/demo/manifest.json` uses this draft (`format_version: "0.1-draft"`):

| Key | Meaning |
| --- | --- |
| `format`, `format_version` | manifest format identifier and version |
| `package_id`, `version` | package identity; semantic version |
| `created`, `synthetic`, `description`, `licence`, `provenance` | metadata |
| `crs` | CRS of every spatial layer (for example `EPSG:2100`) |
| `study_area` | `core_municipalities`, `buffer_municipalities`, `buffer_rule` (OQ-28 open) |
| `coverage` | per municipality and layer: `missing`, `open data`, `estimated`, `verified` (`synthetic` for demo data) |
| `processing_notes` | list of `DP-NNN` notes behind the data (**required**) |
| `changelog` | list of `{version, date, changes}` |
| `files` | list of `{path, sha256, bytes}` for every file in the package |

## Temporary `demo` schema

Until package import exists, `make seed` loads the synthetic demo dataset into a separate PostgreSQL schema `demo` (Alembic migration `0002`; `backend/src/solidaritynode_backend/demo_seed.py`). **This schema is temporary and will be replaced by data-package import in the platform PR.** Nothing is loaded into `public`.

## Options to evaluate

1. **Directory or zip of GeoPackage + CSV/Parquet + `manifest.json`** (as in the demo): opens in QGIS, simple to check.
2. **Single GeoPackage** containing all layers, tables and the manifest as a table.
3. **Frictionless Data Package** (`datapackage.json`) conventions, extended with spatial metadata.

## Questions to answer before deciding

- Exact layer list and schemas (with ADR 0003 and ADR 0009); large arrays in Parquet (ADR 0008).
- Buffer definition (OQ-28) and how buffer features are marked and reported.
- Import workflow: preview of changes (added, changed, closed features), validation, rollback.
- Signing in addition to checksums? Where are packages published?
- How do runs record the package version for reproducibility (ADR 0017)?

## Decision

Not decided.

## Consequences

To be written. The platform PR replaces the `demo` schema with package import.
