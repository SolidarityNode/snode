# DP-006: Hub package assembly (automated)

| Field | Value |
| --- | --- |
| Status | done (v0.2) |
| Author | SolidarityNode contributors |
| Date | 2026-11-26 |
| Municipality / study area | any study area registered in a hub |
| Used in | every package published by a hub |
| QGIS version | not used; `layers.gpkg` opens in QGIS 3.x |
| Reproducible file | `backend/src/solidaritynode_backend/services/hub/publish.py` (job `hub_publish`) |

## Purpose
Assemble a versioned data package (ADR 0013, schema 2.1) for one study area from the curated
features of the hub (DP-003, DP-004).

## Sources
`hub_features`, the latest `groups` and `services` sources, the processing records since the
previous version.

## Coordinate reference system
The hub CRS, declared in every table of `layers.gpkg` and in the manifest.

## Steps
1. **Municipalities**: the core ones and the buffer by the study area's rule (OQ-28 open).
2. **Features valid at the publish date** of those municipalities (units within the distance
   for the `distance` rule), plus every feature an earlier version had, so the installation's
   import never sees a feature vanish. Nodes inside the units plus the nodes units and
   facilities point to; edges with both ends kept. `role` is `core` or `buffer` by
   municipality.
3. **Write** `layers.gpkg` (reproducible bytes), `tables/*.csv`, `manifest.json` with
   coverage of every municipality and layer (the coverage matrix), layer licences and
   attributions, sources with checksums, `provenance` (processing records), changelog (earlier
   entries plus a generated entry), file checksums.
4. **Validate** with the installation's reader (`services/packages.read_package`); a package
   that would not import is not published.
5. **Store** the directory and a `.zip` under `packages/<study area>/`; the row becomes
   immutable (database trigger). A fingerprint of every feature is kept for the propagation
   check and the next version.

## Output
`<hub storage>/packages/<study area>/<version>/` and `<study area>-<version>.zip`.

## Checks
- [x] Published packages import into a municipal installation (test
      `test_onboarding_b_marks_a_for_update_and_b_arrives_as_verified_buffer`, e2e test)
- [x] Shared features have identical ids, geometry and attributes in every package (test
      `test_shared_features_have_the_same_ids_in_every_package`)

## Assumptions and limitations
- Version: minor for additions, closures or updates; patch when every change comes from
  changesets marked as corrections; major only for a schema change.
- Packages are not signed (ADR 0013, ADR 0014).
