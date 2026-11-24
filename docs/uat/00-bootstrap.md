# UAT 00: Bootstrap

Manual acceptance test for the bootstrap PR (`chore/bootstrap`). It checks that the skeleton
installs, starts, shows which build is running, loads the synthetic demo data and keeps its
safety rules. No scientific results exist yet.

Before you start, complete the one-time setup in [`README.md`](README.md#1-one-time-setup-on-a-fresh-machine-windows-with-wsl2-and-podman).
Tick each step when the result matches. If a step does not match, stop and report it (step
number, what you saw, build commit) as a comment on the PR.

## A. Install and automated checks

| # | Do this | Expected result | OK |
| --- | --- | --- | --- |
| 1 | `git fetch origin && git switch chore/bootstrap && git pull` | `Your branch is up to date` (or a fast-forward). | ☐ |
| 2 | `git rev-parse --short=12 HEAD` and write the value down | A 12-character commit id, for example `d4ab3121a0b2`. Called **COMMIT** below. | ☐ |
| 3 | `make setup` | Ends without `Error`. If `.env` did not exist: `Created .env from .env.example`. No `WARNING` about missing keys. | ☐ |
| 4 | `make lint test` | Ends without `Error`; the three test runs report `passed` (core, backend) and `Tests … passed` (frontend). | ☐ |

## B. Start a clean environment

| # | Do this | Expected result | OK |
| --- | --- | --- | --- |
| 5 | `make uat`, type `yes` when asked | After a few minutes: `seed: loaded synthetic demo dataset …` with a row count per table (for example `demo.spatial_units 8 rows`), then `UAT environment ready (build COMMIT…)` and five addresses. | ☐ |
| 6 | `make ps` | Three containers `db`, `backend`, `frontend`, each `Up … (healthy)`; ports start with `127.0.0.1:`. | ☐ |

## C. The application

| # | Do this | Expected result | OK |
| --- | --- | --- | --- |
| 7 | Open http://127.0.0.1:8080 | Page titled **SolidarityNode** with links **Home** and **Health**. | ☐ |
| 8 | Look at the footer | `AGPL-3.0 · synthetic data only · backend 0.0.1 (COMMIT, development) · frontend COMMIT`. Both commits equal COMMIT. | ☐ |
| 9 | Click **Health** | `Backend status: ok (backend 0.0.1, core 0.0.1)`. | ☐ |
| 10 | Open http://127.0.0.1:8000/health | `{"status":"ok"}` | ☐ |
| 11 | Open http://127.0.0.1:8000/version | JSON with `"git_commit":"COMMIT…"` and `"app_env":"development"`. | ☐ |
| 12 | Open http://127.0.0.1:8000/docs | Page **SolidarityNode API** listing `GET /health`, `GET /health/ready`, `GET /version`. | ☐ |
| 13 | `make down`, then open http://127.0.0.1:8080/health | The page does not load (the stack is stopped). | ☐ |
| 14 | `make up`, wait for it to finish, then reload http://127.0.0.1:8080/health | `Backend status: ok` again. | ☐ |
| 15 | Stop the backend only: `make stop SERVICE=backend`, then reload the Health page | An error message instead of `Backend status: ok`; the footer shows `backend unavailable`. Then `make up`, `make wait`, reload: `ok` again. | ☐ |

## D. Synthetic demo data in the database

Open the database shell with `make db-shell`, then type each query (end with `;`, press Enter).

| # | Do this | Expected result | OK |
| --- | --- | --- | --- |
| 16 | `\dn` | Schemas include **`demo`** and `public`. | ☐ |
| 17 | `SELECT version_num FROM alembic_version;` | `0002` | ☐ |
| 18 | `SELECT unit_id, municipality_id, role FROM demo.spatial_units ORDER BY 1;` | 8 rows: `A1`–`A6` with `M-A` and `core`; `B1`, `B2` with `M-B` and `buffer`. | ☐ |
| 19 | `SELECT f.facility_id, m.municipality_id FROM demo.facilities f JOIN demo.municipalities m ON ST_Within(f.geom, m.geom) ORDER BY 1;` | `F1`, `F2`, `F3` in `M-A`; **`F4` in `M-B`** (the facility across the border). | ☐ |
| 20 | `SELECT DISTINCT ST_SRID(geom) FROM demo.spatial_units;` | `2100` | ☐ |
| 21 | `SELECT mode, travel_time_min FROM demo.hand_check_travel_times WHERE scenario_id = 'baseline' AND unit_id = 'A4' AND facility_id = 'F2' ORDER BY mode;` | `car 15` and `walk 90`. Check by hand: 5 + 2 + 0.5 km at 2 and 12 min/km (see the demo README). | ☐ |
| 22 | `SELECT scenario_id, travel_time_min FROM demo.hand_check_travel_times WHERE mode = 'walk' AND unit_id = 'A1' AND facility_id = 'F2' ORDER BY 1;` | `baseline 66` and `C-DEMO-REF 78`: closing edge E02 makes the trip longer. | ☐ |
| 23 | `SELECT body->'facility_severities', body->'network_disruption'->'affected_link_ids' FROM demo.scenarios;` | `{"F1": 0.5}` and `["E02"]`. | ☐ |
| 24 | `\dt public.*` | Only `alembic_version` and `spatial_ref_sys`: nothing from the demo is in `public`. | ☐ |
| 25 | `\q` | Back at the normal prompt. | ☐ |
| 26 | `make seed` (run it twice) | Both runs print the same row counts (`demo.spatial_units 8 rows`, `demo.hand_check_travel_times 128 rows`). | ☐ |

Optional: open `data/synthetic/demo/demo.gpkg` in QGIS. Expected: four layers
(`municipalities`, `spatial_units`, `unit_centroids`, `facilities`) in EPSG:2100, a 4 × 8 km
grid in open sea; F4 just east of the municipal boundary.

## E. Safety rules

| # | Do this | Expected result | OK |
| --- | --- | --- | --- |
| 27 | `make check-config APP_ENV=production` | Fails with `placeholder secrets must be replaced before starting: database_url (password)`. The password is **not** printed. | ☐ |
| 28 | `make check-config` | `configuration OK (APP_ENV=development)` | ☐ |
| 29 | `make reset`, then type `no` | `Aborted.`; `make ps` still shows the three containers, and step 18 still returns 8 rows. | ☐ |
| 30 | `git status --short` | No changes listed (in particular `.env` and `data/local/` never appear). | ☐ |
| 31 | `grep -n '"127.0.0.1:' compose.yaml` | Three port lines (database, backend, frontend), all starting with `127.0.0.1:`. | ☐ |

## F. Finish

| # | Do this | Expected result | OK |
| --- | --- | --- | --- |
| 32 | `make down` | Containers stopped. The database is kept for next time; `make uat` starts from scratch again. | ☐ |

If every step matches, tick **"UAT passed by maintainer"** in the PR.
