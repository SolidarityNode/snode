# DP-005: Synthetic national sources and facility files for the hub

| Field | Value |
| --- | --- |
| Status | done |
| Author | SolidarityNode contributors |
| Date | 2026-11-26 |
| Municipality / study area | four fictional municipalities M-A, M-B, M-C, M-D |
| Used in | hub tests (`backend/tests/hub/`), `make uat-hub`, `make test-e2e`, UAT 02; no paper |
| QGIS version | not used (built by script); the GeoPackages open in QGIS 3.x |
| Reproducible file | `scripts/generate_hub_sources.py` (deterministic, standard library only) |

## Purpose
Raw sources as a national provider would deliver them, but covering **four** municipalities, so
that onboarding only some of them, reusing ids across onboardings and propagating updates can be
tested; plus facility files for the import screen.

## Sources
| Source | Version | Licence | File |
| --- | --- | --- | --- |
| Synthetic demo dataset (DP-001) | constants of `generate_demo_data.py` | AGPL-3.0-or-later | `data/synthetic/demo/hub/` (committed) |

## Coordinate reference system
EPSG:2100, as DP-001 (fictional grid in open sea).

## Steps
1. Municipalities A (0–6 × 0–4 km) and B (6–8 × 0–4 km) with their units, population, groups,
   services, facilities and network are those of DP-001. **C** (0–3 × 4–6 km, units C1, C2)
   touches A4 and A5 only; **D** (8–10 × 0–4 km, units D1, D2) touches B only.
2. Five edges are added: E14 (A4–C1), E15 (C1–C2), E16 (B1–D1), E17 (D1–D2), E18 (B2–D2).
   Facility access nodes N-F1 … N-F4 stay in the network.
3. Population of C1, C2, D1, D2 is invented.
4. `sources/sources.json` holds the registration metadata (version `2026-11`, `DP-005`,
   quality `open_data`, `synthetic: true`).
5. `imports/`: `facilities-M-A.csv` (F1–F3 of DP-001, verified), `facilities-M-B.csv` (F4),
   `facilities-M-A-errors.csv` (row 2 without name, row 3 unknown service `S-XX`, row 4 unit
   `visit` for an appointment service, row 5 point inside M-B), `facilities-M-A-personal.csv`
   (columns `contact_person`, `mobile`, and a mobile number in `public_phone` of row 2),
   `facilities-M-A-update.csv` (HF-000002 throughput 100 → 90, new day centre 5).

## Output
`data/synthetic/demo/hub/sources/` (3 GeoPackages, 3 CSV, `sources.json`) and
`data/synthetic/demo/hub/imports/` (5 CSV).

## Checks
- [x] Running the script twice gives identical files (GeoPackages written with
      `reproducible=True`)
- [x] Onboarding A selects A, B, C; onboarding B selects A, B, D (tests)

## Assumptions and limitations
Everything is invented; no value is a research parameter.
