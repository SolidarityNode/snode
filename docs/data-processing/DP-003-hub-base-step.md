# DP-003: Hub onboarding, base step (automated)

| Field | Value |
| --- | --- |
| Status | done (v0.2; to be revisited with real sources) |
| Author | SolidarityNode contributors |
| Date | 2026-11-26 |
| Municipality / study area | any municipality onboarded in a hub, plus its buffer |
| Used in | every package published by a hub (`processing_notes`, `provenance` of the manifest) |
| QGIS version | not used: PostGIS in the hub database. A manual QGIS alternative may live in `data-processing/qgis/` |
| Reproducible file | `backend/src/solidaritynode_backend/services/hub/base.py` (job `hub_onboard_base`) |

## Purpose
Prepare the base layers (boundaries, spatial units, population, network) of one municipality and
its buffer from registered national raw sources, with stable ids, so facilities can be imported
and packages published. Each run writes a **processing record** (inputs with versions and
SHA-256, parameters, outputs, checks) that cites this note.

## Sources
The **latest registered source** of each type at the time the step is queued (see the hub
**Sources** screen); the record lists name, version, SHA-256, licence and attribution.

| Layer type | Format | Required columns |
| --- | --- | --- |
| `boundaries` | GeoPackage, polygon table | `municipality_code`, `name` |
| `spatial_units` | GeoPackage, polygon table | `unit_code`, `name`, `municipality_code` (optional `centroid_node_code`) |
| `network` | GeoPackage, point table and line table | nodes: `node_code` (optional `kind`); edges: `edge_code`, `from_node`, `to_node`, `length_m`, `travel_time_walk_min`, `travel_time_car_min` (optional `closable`) |
| `population` | CSV (UTF-8, comma) | `unit_code`, `group_id`, `population` |
| `groups`, `services` | CSV | as the package tables of ADR 0013 |

The spatial unit is **data, not an assumption**: whatever polygons the registered source holds
(communities, census blocks, grid cells) become the units. The choice of unit for large
municipalities is an open item of the Paper 1 spec (ADR 0013).

## Coordinate reference system
Output in `SOLIDARITYNODE_HUB_CRS` (default EPSG:2100). A source in another EPSG CRS is
reprojected with PostGIS `ST_Transform` while it is read; the report lists it
(`hub.base.reprojected`).

## Steps
1. **Find the municipality** in the boundaries source (streamed row by row).
2. **Select the area**: the municipality and its buffer (`SOLIDARITYNODE_HUB_BUFFER_RULE`):
   `whole_neighbouring_municipalities` (default, as in the demo packages) keeps every
   municipality whose boundary intersects it; `distance` keeps the units within
   `SOLIDARITYNODE_HUB_BUFFER_DISTANCE_M` of it. **OQ-28 is open**: this is a configurable
   placeholder, not a method choice. Only rows whose bounding box meets the area are decoded
   (bounding-box prefilter on the GeoPackage blob header), so national files are never loaded
   whole.
3. **Spatial units** of the selected municipalities (or within the distance).
4. **Population** rows of those units (CSV streamed).
5. **Network**: nodes inside the selected units; edges whose two ends are kept (edges leaving
   the area are counted and left out).
6. **Unit nodes**: `centroid_node_code` of the source if present; otherwise the network node
   nearest to `ST_PointOnSurface(unit)`. *Assumption*, reported as `hub.base.centroid_rule`.
7. **Ids**: official codes of the source (`municipality_code`, `unit_code`, `node_code`,
   `edge_code`). A unit or edge without a code gets a hub id (`HU-…`, `HE-…`) found again by the
   SHA-256 of its source geometry. A feature already present (earlier onboarding of a
   neighbour) is **reused**; changed data updates it; a feature that disappeared from the
   source within the selected municipalities is **closed** (`valid_to`), never deleted.
8. **Checks** (below). Any error stops the step and nothing is stored (one transaction).
9. **Status**: the municipality goes from `not_started` to `base_ready`; buffer municipalities
   get an onboarding row (status `not_started`).

## Output
| Table | Content |
| --- | --- |
| `hub_features` | `municipalities`, `spatial_units` (with `population` and `centroid_node_id`), `network_nodes`, `network_edges`; `quality` from the source, `processing_note` `DP-003` |
| `hub_processing_records` | one record per run (kind `onboarding_base`) |

## Checks
- [x] CRS of every source table is an EPSG code (error otherwise); reprojection reported
- [x] Geometry validity of municipalities and units (`ST_IsValid`; error)
- [x] Duplicate unit codes (error); nodes without code (error); edges with missing or negative
      length or travel times (error)
- [x] The core municipality has at least one unit (error)
- [x] Network connectivity: number of connected parts (info); units whose node is outside the
      largest part (warning)
- [x] Population: unknown group, non-integer value, duplicate unit and group (errors); units
      missing a group (warning); total per municipality (info) and the stored total equals the
      source rows read for the same units (error if not)
- [x] Rerun with the same sources changes nothing (test `test_rerun_is_idempotent_and_neighbours_reuse_ids`)

## Assumptions and limitations
- Unit nodes by nearest node (step 6) when the source gives none.
- Transit, DEM and susceptibility sources can be registered but are not processed in v0.2.
- A changed source is detected only when the base step is run again for a municipality.

## Open issues
OQ-28 (buffer definition); the choice of spatial unit for large municipalities (Paper 1 spec).
