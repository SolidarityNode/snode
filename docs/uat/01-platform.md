# UAT 01: Platform mechanics

Manual acceptance test for the platform PR (`feat/platform-mechanics`). It checks that a user
can, in the browser and with synthetic data only, look at the study area, create and save a
scenario, run it in the background, follow it, see and export results, compare them with the
baseline, import a new data package version and find everything again. **No scientific method
exists yet:** every result comes from the *diagnostic model* and carries a banner saying so.

Before you start, complete the one-time setup in [`README.md`](README.md#1-one-time-setup-on-a-fresh-machine-windows-with-wsl2-and-podman).
Tick each step when the result matches. If a step does not match, stop and report it (step
number, what you saw, build commit from the footer) as a comment on the PR.

Screenshots of every screen, taken on the synthetic data while walking through this checklist,
are in [`screenshots/01-platform/`](screenshots/01-platform/).

Two browsers help: use a normal window for the analyst and a private window for the
administrator or viewer, so both stay logged in.

## A. Start from a clean state

| # | Do | Expected result | ✓ |
| --- | --- | --- | --- |
| 1 | In the terminal: `make setup`, then `make uat` and type `yes` | After a few minutes it prints "UAT environment ready", the address `http://127.0.0.1:8080` and two demo accounts: `demo-admin / demo-admin-pass` and `demo-analyst / demo-analyst-pass`. | ☐ |
| 2 | `make ps` | Four containers are `Up`: `db`, `backend`, `worker`, `frontend` (db, backend and frontend say `healthy`). | ☐ |

## B. Log in

| # | Do | Expected result | ✓ |
| --- | --- | --- | --- |
| 3 | Open http://127.0.0.1:8080 | The **Log in** page opens. The footer shows `no data imported` or the data version, then `backend 0.0.1 (<commit>, development) · frontend <commit>`. The commit matches `git rev-parse --short=12 HEAD`. | ☐ |
| 4 | Log in as `demo-analyst` with the password `wrong-password` | Red message "Wrong username or password." | ☐ |
| 5 | Log in as `demo-analyst` / `demo-analyst-pass` | The **Study area** page opens. The header says "Signed in as demo-analyst (analyst)". There is no **Admin** link. The footer shows `data demo-study-area-a 1.0.0`. | ☐ |

## C. Study area

| # | Do | Expected result | ✓ |
| --- | --- | --- | --- |
| 6 | Look at the page | "Data package demo-study-area-a, version 1.0.0 (2026-11-24). **Synthetic data.**" An orange warning says "Edge-effect warning for units A3, A6 …". | ☐ |
| 7 | Look at the map | Six squares of municipality A (dark solid outline, dotted = open data) and two squares of B on the right (grey **dashed** outline, **hatched** = estimated). A3 and A6 (next to B) have a thick orange outline. Three blue dots (facilities F1, F2, F3) and lines (network). Without internet, or with `SOLIDARITYNODE_BASEMAP=blank`, the background is empty; otherwise it shows sea and "© OpenStreetMap contributors". The legend below explains every symbol in words. | ☐ |
| 8 | Click the dot **F1** on the map (or open "facilities" in **Features (text list)** and click `F1 · Community centre 1`) | The **Selected feature** panel shows F1: municipality M-A, role core, quality "verified by the municipality", valid from 2026-01-01, and the services with places, staff and throughput. | ☐ |
| 9 | Click unit **A3** | The panel shows A3, role core, quality open data, the edge-effect explanation and population by group. | ☐ |
| 10 | Click the line **E02** (between A2 and A3) | The panel shows edge E02 with length 2000, walking time 24, car time 4 and "Can be closed: true". | ☐ |
| 11 | Look at **Data coverage per municipality and layer** | M-A: facilities `verified`, transit `missing`. M-B: population `estimated`, facilities **`missing`** (in red), transit `missing`. | ☐ |
| 12 | Press **Tab** until the map has a blue focus frame, then press the arrow keys and `+` / `-` | The map pans and zooms with the keyboard. | ☐ |
| 13 | Switch **Language** to Ελληνικά, then back to English | All texts change to Greek (menu, titles, legend, table headings) and back. | ☐ |

## D. Scenarios list

| # | Do | Expected result | ✓ |
| --- | --- | --- | --- |
| 14 | Click **Scenarios** | "My scenarios: You have no scenarios yet." Under **Shared scenarios**: "Baseline (no changes)", owner "system", latest run **succeeded** (1.0.0). | ☐ |

## E. Scenario editor

| # | Do | Expected result | ✓ |
| --- | --- | --- | --- |
| 15 | Click **New scenario** | The editor opens with a map. Under **Validation** an error about the name; **Save** is greyed out. | ☐ |
| 16 | Type the name `UAT close E02` and choose **Visibility: shared** | Within a second **Validation** says "The scenario is valid for the active data." and **Save** becomes active. | ☐ |
| 17 | Click the line **E02** on the map (or open **Facilities and edges (text list)** and click **Close edge E02**) | E02 turns orange and dashed. **Changes relative to the baseline** shows "Closed edges: E02" with **walking** and **car** ticked. Validation now shows an error "a disruption scenario must state its rationing case (OQ-24)"; **Save** is greyed out. | ☐ |
| 18 | In the text list, try **Close edge E01** | The button is greyed out and says "(cannot be closed)". | ☐ |
| 19 | Set **Rationing case (OQ-24)** to **uniform** | Validation is valid again. | ☐ |
| 20 | Click the dot **F1** (or **Select F1**). In **Selected facility** type `0.5` in **Disruption severity DS** | The list shows "Facility F1: severity 0.5". F1 turns orange on the map. | ☐ |
| 21 | Type `2` in the severity field | Validation shows an error ("less than or equal to 1"); **Save** is greyed out. Change it back to `0.5`. | ☐ |
| 22 | In **Capacity change** choose service `S-HC`, input **staff**, **percent of baseline**, amount `20`, click **Add change** | The list shows "Facility F1, S-HC: staff 20 %". | ☐ |
| 23 | Click **Save** | "Saved as version 1." The title becomes "Scenario: UAT close E02" with "Version 1, created against data 1.0.0, owner demo-analyst". | ☐ |
| 24 | Change the description to `second version` and click **Save as new version** | "Saved as version 2." | ☐ |
| 25 | Go back to **Scenarios**, click **New scenario**, name it `UAT F3 staff`, select **F3**, add a capacity change S-HC staff, **absolute amount** `1`, **Save** | Saved as version 1. (This scenario refers to F3, which data version 1.1.0 closes; see step 47.) | ☐ |

## F. Run, progress and results

| # | Do | Expected result | ✓ |
| --- | --- | --- | --- |
| 26 | Open **UAT close E02** from **Scenarios** and click **Run this version** | The run page opens with a yellow banner "**Diagnostic model: not a research result.** …". **Status** goes from **queued** to **running** with a moving progress bar and "… % done", then to **succeeded** (a few seconds). | ☐ |
| 27 | Under **Show** choose **Group** Older people, **Service** Home care, **Indicator** "Walking time to nearest facility (diagnostic)" | The map colours the six A units; B units are grey and dashed ("Not reported"). A3 and A6 have an orange outline. The table row **Unit A3** shows value `66 min (deterministic, no uncertainty)`, **Before the scenario** `30`, **Changed: changed**, and "⚠ edge effect (OQ-28)". | ☐ |
| 28 | Choose **Indicator** "Diagnostic noise (meaningless)" | Each value is shown with an interval, for example `0.05 [-1.6 – 1.7] 90 % interval`. | ☐ |
| 29 | Look below the table | "Hand-check of baseline travel times: 48 of 48 match. With the scenario: 48 of 48 match." **What changed per unit** lists A2 ("F1: S-HC staff 4 -> 4.8; F1: DS = 0.5 (recorded only); edge E02 closed") and A3 ("edge E02 closed"). The severity is recorded only: no method turns it into lost capacity yet. | ☐ |
| 30 | Look at **Reproducibility** | Scenario and version (`UAT close E02 (v2)`), data package `demo-study-area-a 1.0.0`, code version (the commit), model `diagnostic-v0 0.1.0`, seed `1`, configuration, input hash, created and finished times. | ☐ |
| 31 | Click **Export CSV** and **Export GeoPackage** | Two zip files download. The CSV zip contains `results.csv`, `travel_times.csv`, `unit_changes.csv` and `metadata.json` (with all reproducibility fields and the diagnostic notice). The GeoPackage opens in QGIS with a `results` layer of unit polygons in EPSG:2100. | ☐ |
| 32 | Go to **Scenarios** | **UAT close E02** shows its latest run **succeeded** (1.0.0). | ☐ |
| 33 | Click **Run** on the row of **UAT close E02** | The **same** run opens again at once (same reproducibility fields and times): identical inputs reuse the existing result. | ☐ |

## G. Cancel

| # | Do | Expected result | ✓ |
| --- | --- | --- | --- |
| 34 | Open **UAT close E02**, set **Random seed** to `2` and **Pause after each step** to `3`, click **Run this version**, then click **Cancel run** while it is running | Within a few seconds the status becomes **cancelled** with "Cancelled by a user while running." No results are shown. | ☐ |

## H. Compare with the baseline

| # | Do | Expected result | ✓ |
| --- | --- | --- | --- |
| 35 | Open the succeeded run of step 26 (Scenarios → status link) and click **Compare with baseline** | The **Compare runs** page shows the diagnostic banner, "Same data version 1.0.0", three maps (A: UAT close E02, B: Baseline (no changes), Difference A − B) and a legend. | ☐ |
| 36 | Choose Home care and the walking indicator | Row A3: A `66 min`, B `30 min`, difference `36`. Units without a change show difference `0`. | ☐ |

## I. Worker stops during a run

| # | Do | Expected result | ✓ |
| --- | --- | --- | --- |
| 37 | Start a run of **UAT close E02** with seed `3` and pause `5` (about 30 seconds). While it is **running**, in the terminal: `make stop SERVICE=worker` | Within a few seconds the run page shows **failed** with "The run failed: Interrupted: the worker (worker) stopped while this run was running (…). No results were stored. Start the run again." | ☐ |
| 38 | `make up`, wait for `make ps` to show the worker `Up`, then run **UAT close E02** with seed `3` again | A **new** run is queued (the failed one is not reused) and **succeeds**. | ☐ |

## J. Administration: users and data packages

| # | Do | Expected result | ✓ |
| --- | --- | --- | --- |
| 39 | In a private window log in as `demo-admin` / `demo-admin-pass`, click **Admin** | **Data packages** shows "Active data: demo-study-area-a 1.0.0" and one imported version (active). **Users** lists demo-admin and demo-analyst. | ☐ |
| 40 | Under **New user** create `uat-viewer`, password `uat-viewer-pass`, role **viewer** | The user appears in the table. | ☐ |
| 41 | Under **Packages available on the server** click **Preview demo-1.1.0** | A preview appears: status "update", compared with active 1.0.0, schema 1.0. In **Changes per layer**, facilities: added **F4**, changed **F2 (services)**, closed **F3**, unchanged 1; all other layers have no changes. **Coverage changes:** M-B / facilities: missing → verified. The changelog shows 1.0.0 and 1.1.0. Nothing is imported yet (footer and active version still 1.0.0). | ☐ |
| 42 | Click **Confirm import** | "Imported as data version 2; it is now active." with a link **Baseline run for the new data**, and "Scenarios that refer to closed or missing features: UAT F3 staff: facility F3: closed or missing …". | ☐ |
| 43 | Click **Preview demo-1.1.0** again | Status "same version already imported"; the button says "Already imported (nothing to do)". | ☐ |
| 44 | In the terminal: `make import-package PKG=data/synthetic/packages/demo-1.1.0` | The preview is printed and the command ends with "This version is already imported: nothing to do." | ☐ |
| 45 | In the terminal: `cp -r data/synthetic/packages/demo-1.1.0 /tmp/broken && echo "x" >> /tmp/broken/tables/groups.csv && make import-package PKG=/tmp/broken` | Refused: "import-package: checksum mismatch for tables/groups.csv: the file is damaged or was changed". Nothing is imported. | ☐ |
| 46 | Back in the browser, under **Imported versions** | Two versions: 1.1.0 **active**, 1.0.0 **kept**. | ☐ |

## K. After the update (analyst window, reload the page)

| # | Do | Expected result | ✓ |
| --- | --- | --- | --- |
| 47 | Open **Scenarios** | **UAT F3 staff** shows "Needs attention with the current data: facility F3: closed or missing …" and has no **Run** button. **UAT close E02** still lists its latest run on 1.0.0. The footer shows data 1.1.0. | ☐ |
| 48 | Open **Study area** | No edge-effect banner; A3 and A6 have no orange outline. A fourth dot **F4** appears in B. **F3** is white with a grey dashed ring; clicking it shows "Valid to (closed) 2026-12-01" and "Closed true". Coverage: M-B facilities **verified**. | ☐ |
| 49 | Open the run of step 26 | An orange note: "This run used data 1.0.0; the active data is 1.1.0." with **Rerun on data 1.1.0**. Its results are unchanged (A3 still 66). | ☐ |
| 50 | Click **Rerun on data 1.1.0** and wait for **succeeded**; choose Home care and walking | A3 now shows `18 min` (F4 across the border) without an edge-effect warning; A1 shows `30 min` (F3 closed, so A1 goes to F1). | ☐ |
| 51 | Under **Runs of this scenario**, next to the 1.0.0 run, click **Compare with this run** | The comparison page says "Same scenario across data versions 1.0.0 → 1.1.0. Only allowed because both runs belong to the same scenario." Row A3: A `18 min`, B `66 min`, difference `-48`. | ☐ |
| 52 | Change the address to `/runs/<id of this 1.1.0 run>/compare?with=<id of the Baseline run on 1.0.0>` (ids are in the addresses of those run pages) | Refused with a message: "the runs use different data versions (1.1.0 and 1.0.0); compare runs on the same data version, or two runs of the same scenario". | ☐ |

## L. Viewer

| # | Do | Expected result | ✓ |
| --- | --- | --- | --- |
| 53 | In the private window log out, log in as `uat-viewer` / `uat-viewer-pass` | No **Admin** link, no **New scenario** button. **Shared scenarios** lists Baseline and **UAT close E02**, but **not** UAT F3 staff if it is private (it is private by default). | ☐ |
| 54 | Open a run of **UAT close E02** | Results, map, table and exports are visible; there is no **Cancel**, **Run** or **Rerun** button. | ☐ |
| 55 | Open http://127.0.0.1:8080/admin | "This page is for administrators." | ☐ |

## M. Clean up

| # | Do | Expected result | ✓ |
| --- | --- | --- | --- |
| 56 | `make down` | All containers stop; `make up` later keeps the data. `make uat` starts again from zero. | ☐ |
