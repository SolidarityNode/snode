# 0013. Data packages: format, versioning, checksums and buffer

- Status: Accepted for v0.1, to be revisited
- Date: 2026-11-24 (accepted for v0.1: 2026-11-25)
- Related: Spec 00 §3 (Data package, Study area, Onboarding, Stable identifiers), OQ-28; ADR 0003, 0008, 0009, 0012; `docs/data-processing/README.md` rule 9

## Context

Spec 00 §3: a data package is a **versioned (semantic versioning), checksummed** bundle for one study area **plus a buffer** of neighbouring units (OQ-28), with layer coverage, changelog and provenance, produced by the hub and imported by an installation after a preview of changes. Features keep stable ids and carry `municipality_id`, `role` (core | buffer), `quality`, `valid_from` / `valid_to`. Each package's `manifest.json` lists the `DP-NNN` processing notes behind its data (`docs/data-processing/README.md`, rule 9).

## History

The bootstrap used a draft manifest (`format_version: "0.1-draft"`, still in
`data/synthetic/demo/manifest.json`, the source dataset of DP-001) and a temporary `demo`
schema loaded by `make seed`. Both are replaced by the format and import below (migration 0003
drops the `demo` schema; the demo packages are built by DP-002).

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

**Accepted for v0.1, to be revisited: option 1, a directory or archive (`.zip`, `.tar`,
`.tar.gz`) with a `manifest.json`, GeoJSON layers and CSV tables.** Schema version `1.0`.

`manifest.json` keys: `format` (`solidaritynode-data-package`), `schema_version` (`MAJOR.MINOR`;
an installation reads one major version and refuses others with a clear message), `package_id`,
`version` (semantic versioning), `created`, `synthetic`, `description`, `crs` (`EPSG:n`),
`study_area` (`core_municipalities`, `buffer_municipalities`), `buffer` (`rule`, `description`;
the definition is open, OQ-28), `coverage` (per municipality and layer `boundaries`,
`population`, `network`, `facilities`, `transit`: `status` `missing | open_data | estimated |
verified` and the layer `version`), `sources` (name, licence, attribution), `processing_notes`
(`DP-NNN`, required), `changelog` (must contain the package version), `files` (`path`, `sha256`,
`bytes` for every file; unlisted files are refused).

Files: `layers/{municipalities,spatial_units,facilities,network_nodes,network_edges}.geojson`,
`tables/{groups,services,population,facility_services}.csv`,
`checks/hand_check_travel_times.csv` (optional). Every feature has a **stable id** (the same in
every package and installation; for units the official statistical code where one exists,
otherwise a hub-assigned id) and `municipality_id`, `role` (`core | buffer`), `quality`
(`open_data | estimated | verified_by_municipality`), `valid_from`, `valid_to` and
`processing_note`. Features are closed with `valid_to`, never deleted; a feature is open when
`valid_to` is empty or after the package date.

Import (`make import-package PKG=…` or the Admin screen): validate the manifest, schema version
and checksums → preview against the active version (added, changed, closed features per layer,
coverage changes) → import after confirmation, in one transaction. Rules: the same version with
the same manifest is a no-op; the same version with different content, a vanished feature or an
incompatible schema is refused. Every imported version is kept (`data_versions`,
`data_features`, `data_records`, `data_coverage`); the new one becomes active; runs keep their
version. Each import creates a baseline run (empty scenario) on the new version. Scenarios are
revalidated against it; references to closed or missing features are reported.

Edge effects (OQ-28, **warning only**): a core unit whose geometry touches a buffer municipality
with `facilities: missing` carries an edge-effect warning on maps and results.

The temporary `demo` schema is dropped by migration 0003.

**Why:** opens in QGIS, simple to check by hand, needs no new library to read or write.

## Consequences

- Every version is stored in full: fine for a municipality, revisit for large study areas.
- No signatures yet (checksums only); no automatic download from the hub.
- Large arrays in packages (Parquet) are not needed yet.
