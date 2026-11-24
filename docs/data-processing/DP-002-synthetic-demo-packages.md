# DP-002: Synthetic demo data packages 1.0.0 and 1.1.0

| Field | Value |
| --- | --- |
| Status | done |
| Author | SolidarityNode contributors |
| Date | 2026-11-24 |
| Municipality / study area | fictional study area A: municipality M-A (core) plus M-B (buffer) |
| Used in | data package `demo-study-area-a` 1.0.0 and 1.1.0 (`data/synthetic/packages/`); tests and UAT only, no paper |
| QGIS version | not used (built by script); the GeoJSON layers open in QGIS 3.x |
| Reproducible file | `scripts/build_demo_packages.py` |

## Purpose
Two versions of one data package in the v0.1 package format (ADR 0013), so tests and UAT can
exercise package import, the preview of changes, coverage, edge-effect warnings, revalidation of
scenarios and reruns on a new data version. Not used in any paper. Every value is a placeholder;
quality labels and coverage statuses are invented.

## Sources
| Source | Version / download date | Licence | File in `data/local/` |
| --- | --- | --- | --- |
| Synthetic demo dataset (DP-001) | generator constants and `hand_check_travel_times.csv` as committed | AGPL-3.0-or-later (repository) | none (output is committed under `data/synthetic/packages/`) |

## Coordinate reference system
EPSG:2100 (GGRS87 / Greek Grid), unchanged from DP-001. GeoJSON layers carry a named `crs`
member (`urn:ogc:def:crs:EPSG::2100`) and the manifest states `"crs": "EPSG:2100"`. The
platform reprojects to EPSG:4326 only for display.

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
   population, network `open_data`, facilities `verified`, transit `missing`; M-B: boundaries
   and network `open_data`, population `estimated`, facilities and transit `missing`.
6. **Version 1.1.0**: add F4 (verified); F2 / S-SD throughput 100 → 90 (correction); F3
   `valid_to = 2026-12-01` (closed, kept). Coverage: facilities `verified` for both
   municipalities, layer version `1.1.0`.
7. **Hand-check table**: copy `data/synthetic/demo/hand_check_travel_times.csv`, keep only rows
   whose facility is open in the version, and replace `scenario_id` by the set of closed edges
   (`""` for the baseline, `E02` for `C-DEMO-REF`). The times are not recomputed.
8. **Write** GeoJSON (`json.dumps(indent=1, sort_keys=True)`) and CSV files, then
   `manifest.json` with the SHA-256 checksum and size of every file.

```bash
python3 scripts/build_demo_packages.py
```

## Output
| File | Layers / tables | Feature count (1.0.0 / 1.1.0) | Key fields |
| --- | --- | --- | --- |
| `layers/municipalities.geojson` | municipalities | 2 / 2 | `municipality_id`, `role` |
| `layers/spatial_units.geojson` | spatial units | 8 / 8 | `unit_id`, `municipality_id`, `role`, `quality` |
| `layers/facilities.geojson` | facilities | 3 / 4 (1 closed) | `facility_id`, `node_id`, `unit_id`, `valid_to` |
| `layers/network_nodes.geojson` | network nodes | 12 / 12 | `node_id`, `unit_id` |
| `layers/network_edges.geojson` | network edges | 13 / 13 | `edge_id`, `from_node_id`, `to_node_id`, `closable` |
| `tables/groups.csv`, `services.csv`, `population.csv` | attributes | 3, 2, 24 | |
| `tables/facility_services.csv` | capacity inputs | 4 / 6 | `facility_id`, `service_id` |
| `checks/hand_check_travel_times.csv` | expected times | 96 / 96 | `closed_edges`, `mode`, `unit_id`, `facility_id` |

## Checks
- [x] CRS is EPSG:2100 in every layer and in the manifest
- [x] Feature counts as in the table above (backend test `test_packages.py`)
- [x] Building twice gives byte-identical output (backend test `test_demo_packages_are_current`)
- [x] Checksums verified on import (`make import-package`)
- [x] Spot checks: the platform's diagnostic model reproduces every hand-check time (core test
  `test_diagnostic.py`)

## Assumptions and limitations
- The buffer is the whole neighbouring municipality, a demo choice only: the buffer definition
  is open (OQ-28).
- Straight edge geometries are for display only.

## Open issues
- OQ-28: buffer definition and whether buffer demand competes for capacity.
