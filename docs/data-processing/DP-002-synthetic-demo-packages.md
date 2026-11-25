# DP-002: Synthetic demo data packages 1.0.0 and 1.1.0

| Field | Value |
| --- | --- |
| Status | done |
| Author | SolidarityNode contributors |
| Date | 2026-11-24 (schema 2.0: 2026-11-25) |
| Municipality / study area | fictional study area A: municipality M-A (core) plus M-B (buffer) |
| Used in | data package `demo-study-area-a` 1.0.0 and 1.1.0 (`data/synthetic/packages/`); tests and UAT only, no paper |
| QGIS version | not used (built by script); `layers.gpkg` opens in QGIS 3.x |
| Reproducible file | `scripts/build_demo_packages.py` |

## Purpose
Two versions of one data package in package schema 2.0 (ADR 0013), so tests and UAT can
exercise package import, the preview of changes, coverage, edge-effect warnings, revalidation of
scenarios and reruns on a new data version. Not used in any paper. Every value is a placeholder;
quality labels and coverage statuses are invented.

## Sources
| Source | Version / download date | Licence | File in `data/local/` |
| --- | --- | --- | --- |
| Synthetic demo dataset (DP-001) | generator constants and `hand_check_travel_times.csv` as committed | AGPL-3.0-or-later (repository) | none (output is committed under `data/synthetic/packages/`) |

## Coordinate reference system
EPSG:2100 (GGRS87 / Greek Grid), unchanged from DP-001. Every table of `layers.gpkg` declares
SRS 2100 (EPSG) and the manifest states `"crs": "EPSG:2100"`. The platform reprojects to
EPSG:4326 only for display. (Schema 1.0 wrote GeoJSON with EPSG:2100 coordinates and the
obsolete `crs` member, which RFC 7946 does not allow; schema 2.0 replaced it.)

## Steps

1. **Read the DP-001 constants** (municipalities, units, groups, population, services,
   facilities, capacity inputs, edges) from `scripts/generate_demo_data.py`.
2. **Add per-feature metadata** to every municipality, unit, facility, network node and edge:
   `municipality_id`, `role` (`core` | `buffer`), `quality` (`open_data` | `estimated` |
   `verified_by_municipality`), `valid_from` (2026-01-01), `valid_to`, `processing_note`
   (`DP-002`). Invented labels: units of M-A `open_data`, units of M-B `estimated`, facilities
   `verified_by_municipality`, network `open_data`.
3. **Assign facilities and nodes to spatial units** by point-in-square on the synthetic grid
   (F1 → A2, F2 → A6, F3 → A1, F4 → B1); network edges take the municipality of their start node.
4. **Edges**: one feature per stable `edge_id` with `travel_time_walk_min` and
   `travel_time_car_min` (12 and 2 minutes per km, DP-001) and a straight `LineString` between
   its nodes for display; `length_m` stays authoritative (E13 is a winding road).
5. **Version 1.0.0**: facilities F1, F2, F3; F4 (in M-B) left out. Coverage M-A: boundaries,
   population, network `open_data`, facilities `verified_by_municipality`, transit `missing`; M-B: boundaries
   and network `open_data`, population `estimated`, facilities and transit `missing`.
6. **Version 1.1.0**: add F4 (`verified_by_municipality`); F2 / S-SD throughput 100 → 90
   (correction); F3 `valid_to = 2026-12-01` (closed, kept). Coverage: facilities
   `verified_by_municipality` for both
   municipalities, layer version `1.1.0`.
7. **Hand-check table**: copy `data/synthetic/demo/hand_check_travel_times.csv`, keep only rows
   whose facility is open in the version, and replace `scenario_id` by the set of closed edges
   (`""` for the baseline, `E02` for `C-DEMO-REF`). The times are not recomputed.
8. **Write** `layers.gpkg` with the shared standard-library GeoPackage writer
   (`backend/src/solidaritynode_backend/gpkg.py`; one table per layer, typed columns, BOOLEAN
   as 0/1, the SQLite version field of the header fixed so the bytes do not depend on the SQLite
   version), the CSV files (UTF-8, comma, dot decimals, header row), then `manifest.json`
   (schema 2.0, with a licence and attribution per layer) with the SHA-256 checksum and size of
   every file.

```bash
python3 scripts/build_demo_packages.py
```

## Output
| File | Layers / tables | Feature count (1.0.0 / 1.1.0) | Key fields |
| --- | --- | --- | --- |
| `layers.gpkg` table `municipalities` | municipalities | 2 / 2 | `municipality_id`, `role` |
| `layers.gpkg` table `spatial_units` | spatial units | 8 / 8 | `unit_id`, `municipality_id`, `role`, `quality` |
| `layers.gpkg` table `facilities` | facilities | 3 / 4 (1 closed) | `facility_id`, `node_id`, `unit_id`, `valid_to` |
| `layers.gpkg` table `network_nodes` | network nodes | 12 / 12 | `node_id`, `unit_id` |
| `layers.gpkg` table `network_edges` | network edges | 13 / 13 | `edge_id`, `from_node_id`, `to_node_id`, `closable` |
| `tables/groups.csv`, `services.csv`, `population.csv` | attributes | 3, 2, 24 | |
| `tables/facility_services.csv` | capacity inputs | 4 / 6 | `facility_id`, `service_id` |
| `checks/hand_check_travel_times.csv` | expected times | 96 / 96 | `closed_edges`, `mode`, `unit_id`, `facility_id` |

## Checks
- [x] CRS is EPSG:2100 in every GeoPackage table and in the manifest (a layer in another CRS is
  refused, backend test `test_layer_in_another_crs_is_refused`)
- [x] Feature counts as in the table above (backend test `test_packages.py`)
- [x] Building twice gives byte-identical output, also with different SQLite versions (checked
  with 3.46 and 3.53; backend test `test_demo_packages_are_current`)
- [x] Checksums verified on import (`make import-package`)
- [x] Spot checks: the platform's diagnostic model reproduces every hand-check time (core test
  `test_diagnostic.py`)

## Assumptions and limitations
- The buffer is the whole neighbouring municipality, a demo choice only: the buffer definition
  is open (OQ-28).
- Straight edge geometries are for display only.

## Open issues
- OQ-28: buffer definition and whether buffer demand competes for capacity.
