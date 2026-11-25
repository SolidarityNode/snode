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
`.tar.gz`) with a `manifest.json`, one GeoPackage with the layers and CSV tables.** Schema version
`2.0`.

**Why schema 2.0 (GeoPackage instead of GeoJSON).** Schema 1.0 stored the layers as GeoJSON with
coordinates in **EPSG:2100** and the obsolete GeoJSON 2008 `crs` member. RFC 7946 GeoJSON allows
only WGS 84 (EPSG:4326) longitude/latitude, so those files were not valid GeoJSON and other tools
could misread them. Schema 2.0 keeps the **projected CRS** declared in the manifest (distances
and areas in metres, as the network and accessibility need) in a format that declares it
properly: one GeoPackage `layers.gpkg` with one table per layer. It is read and written with the
standard library (`backend/src/solidaritynode_backend/gpkg.py`, the bootstrap's writer plus a
reader), opens in QGIS, and is built byte-for-byte reproducibly. Schema 1.x packages are refused
with the usual "schema version not supported" message.

`manifest.json` keys: `format` (`solidaritynode-data-package`), `schema_version` (`MAJOR.MINOR`;
an installation reads one major version and refuses others with a clear message), `package_id`,
`version` (semantic versioning), `created`, `synthetic`, `description`, `crs` (`EPSG:n`),
`study_area` (`core_municipalities`, `buffer_municipalities`), `buffer` (`rule`, `description`;
the definition is open, OQ-28), `coverage` (per municipality and layer `boundaries`,
`population`, `network`, `facilities`, `transit`: `status` `missing | open_data | estimated |
verified_by_municipality` and the layer `version`), `layers` (per layer: `table` in
`layers.gpkg`, `geometry_type`, `licence`, `attribution`; all required), `sources` (name,
licence, attribution), `processing_notes`
(`DP-NNN`, required), `changelog` (must contain the package version), `files` (`path`, `sha256`,
`bytes` for every file; unlisted files are refused).

Files: `layers.gpkg` with tables `municipalities`, `spatial_units`, `facilities`,
`network_nodes`, `network_edges` (geometry column `geom`, 2D, every table in the manifest CRS:
a layer in another CRS is refused with a message naming both), `tables/{groups,services,
population,facility_services}.csv`, `checks/hand_check_travel_times.csv` (optional). The reader
opens the GeoPackage read-only with `trusted_schema` off, runs `quick_check`, and refuses
non-GeoPackage files, Z/M coordinates and extended geometry blobs.

**CSV dialect**: UTF-8 (a leading byte-order mark is tolerated), comma delimiter, dot as
decimal separator, one header row with the expected column names, numeric columns as plain
numbers. Anything else is refused with a message that says what to change, for example a
semicolon delimiter or comma decimals from a Greek-locale spreadsheet, or a Windows-1253 file.

**One name for the verified state**: `verified_by_municipality`, for feature `quality` and
layer `coverage` alike (coverage used `verified` in schema 1.0; migration 0008 renamed stored
rows). Every feature has a **stable id** (the same in
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

**Rollback**: an administrator can make an earlier imported version active again (Admin screen,
`make activate-version VERSION=x.y.z`, `POST /data-versions/{id}/activate`). Like an import, it
queues a baseline run on that version and revalidates every scenario; nothing is deleted.

**Licences**: every layer carries a licence and an attribution in the manifest (for example
ODbL 1.0 with "© OpenStreetMap contributors" for OpenStreetMap-derived network layers). The
Study area screen lists them. Distributing a package carries the obligations of each layer's
licence (attribution, share-alike for ODbL derivatives, terms of official sources); **legal
review is needed before any package with real data is distributed**.

Edge effects (OQ-28, **warning only**): a core unit whose geometry touches a buffer municipality
with `facilities: missing` carries an edge-effect warning on maps and results.

The temporary `demo` schema is dropped by migration 0003.

**Why:** opens in QGIS, keeps the projected CRS properly declared, simple to check by hand,
needs no new library to read or write.

## Consequences

- Every version is stored in full: fine for a municipality, revisit for large study areas.
- **Checksums detect corruption, not tampering**: whoever can change a file can also change
  the manifest. Packages must be **signed** (and signatures verified) before any automatic
  download from the hub is added (ADR 0014); until then packages are imported by hand from a
  trusted source.
- Large arrays in packages (Parquet) are not needed yet.

### Open for later (from UAT, no code now)

- **How real data corrections reach the hub.** Analysts never upload data: hypothetical changes
  are scenarios (`docs/concepts.md`), and real corrections or new facilities go to the hub and
  arrive in the next package version. How an analyst or a municipality submits such a
  correction (form, file, ticket, with which evidence and quality level) is part of the hub
  onboarding work (ADR 0012, 0014), not decided here.
- **Choice of spatial unit for large municipalities.** For a municipality such as Athens, the
  7 municipal communities are too coarse to show differences in access within it. Which
  spatial unit to use (census tracts, building blocks, a grid) is a method choice for the
  Paper 1 spec (Spec 01), not a package format question; the package format already carries
  whatever unit the spec chooses.
