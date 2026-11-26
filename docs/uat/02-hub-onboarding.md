# UAT 02: Hub onboarding

Manual acceptance test for the hub onboarding PR (`feat/hub-onboarding`, milestone v0.2). It
checks that the hub team can register national sources, onboard a municipality, import and
extend its facilities (including a file with errors and one with personal data), publish a data
package, onboard a neighbour, see the first study area marked "update available", publish its
new version, and that a municipal installation imports both versions with the existing import
screen. **Synthetic data only**; no scientific method is involved.

Before you start, complete the one-time setup in [`README.md`](README.md#1-one-time-setup-on-a-fresh-machine-windows-with-wsl2-and-podman).
Tick each step when the result matches. If a step does not match, stop and report it (step
number, what you saw, build commit from the footer) as a comment on the PR.

Screenshots of the main screens, taken on the synthetic data while walking through this
checklist, are in [`screenshots/02-hub-onboarding/`](screenshots/02-hub-onboarding/).

You use two installations side by side: the **hub** at <http://127.0.0.1:8180> and an empty
**municipal installation** at <http://127.0.0.1:8280>. Use a normal browser window for one and a
private window for the other, so both stay signed in. Your own stack from `make up`
(port 8080) is not touched.

The demo facility files are in `data/synthetic/demo/hub/imports/` of your repository folder
(DP-005).

## A. Start from a clean state

**1.** In the terminal, from the repository folder:

```bash
make setup
make uat-hub
```

Type `yes` when asked. ☐

*Expected:* after a few minutes it prints "Hub UAT ready", the addresses
`http://127.0.0.1:8180` (hub) and `http://127.0.0.1:8280` (municipal installation, "empty: no
data package yet"), and the demo accounts `demo-admin / demo-admin-pass` and
`demo-analyst / demo-analyst-pass`.

**2.** Check the containers:

```bash
podman ps --format "{{.Names}} {{.Status}}"
```

☐ *Expected:* four containers whose names start with `solidaritynode-hub_` (`db`, `backend`,
`worker`, `frontend`) and four starting with `solidaritynode-uat-municipality_`, all `Up`.

## B. Sources

**3.** Open <http://127.0.0.1:8180> and sign in as `demo-admin` / `demo-admin-pass`. ☐

*Expected:* the page **Onboarding of municipalities** opens. A **hub** badge is next to the name
SN Kintsugi. The menu shows **Onboarding, Sources, Facilities, Coverage, Study areas and
packages, Admin, Health**. The table lists **M-A, M-B, M-C, M-D**, each "not started", each with
a button **Start onboarding of …**. The footer ends with a **User guide** link.

**4.** Point at **User guide** in the footer. ☐

*Expected:* the link goes to `https://solidaritynode.github.io/snode/dev/` (a development
build; a production build links to the platform's `major.minor`, for example `.../0.2/`).

**5.** Click **Sources**. ☐

*Expected:* six sources, all version `2026-11`, coverage `national`, licence
`AGPL-3.0-or-later`, processing note `DP-005`, quality "open data", each marked "(synthetic)":

| Name | Layer type | SHA-256 starts with |
| --- | --- | --- |
| Synthetic services | services | `36732e56fd22` |
| Synthetic social groups | social groups | `5c88a39f134f` |
| Synthetic national population | population | `77914562914e` |
| Synthetic national road network | network | `27265f2a77b6` |
| Synthetic national spatial units | spatial units | `e62e64971fbc` |
| Synthetic national boundaries | boundaries | `a2528327597f` |

**6.** In **Register a source**, choose the file
`data/synthetic/demo/hub/sources/boundaries.gpkg`, name `Synthetic national boundaries`, layer
type **boundaries**, version `2026-11`, coverage `national`, licence `AGPL-3.0-or-later`,
attribution `test`, processing note `DP-005`, and click **Register**. ☐

*Expected:* "Source Synthetic national boundaries 2026-11 was already registered with the same
content: nothing changed." The list still has six sources.

**7.** Click **Coverage**. ☐

*Expected:* the **Coverage matrix** lists M-A … M-D with all seven layers (boundaries, spatial
units, population, network, facilities, public transport, susceptibility indicators) **missing**
(in red): nothing is processed yet.

## C. Onboard municipality A

**8.** Click **Onboarding**, then **Start onboarding of M-A**. ☐

*Expected:* "Base step of M-A queued." with a link **Follow its progress**.

**9.** Click **Follow its progress**. ☐

*Expected:* the page **Municipality M-A · Municipality A (fictional)** shows a progress bar
going from **queued** through **running** to **succeeded** (a few seconds), then (reload if
needed) "Onboarding status: **base data ready** · 0 open and 0 closed facilities".

**10.** Look at **Validation report of the base step**. ☐

*Expected:* "Record 1: succeeded (DP-003, …)", "M-A: 42 feature(s) added, 0 changed, 0
closed.", **no errors or warnings**, and six lines under **Information (6)**: "Population of
M-A: 4180 (all groups summed)", the same for M-B (765) and M-C (500); "2 edge(s) with an end
outside the area were left out."; "10 spatial unit(s) were linked to the network node nearest to
a point inside them (DP-003)"; "The network of the area has 1 connected part(s)". **Inputs** lists the six sources
with versions and SHA-256.

**11.** Look at **Status history**. ☐

*Expected:* one row: from "not started" to "base data ready", by `demo-admin`, note "base step,
processing record 1".

**12.** Click **Coverage**, set **Show** to "onboarded municipalities". ☐

*Expected:* only **M-A** ("base data ready"): boundaries, spatial units, population and network
"open data", "version 2026-11", updated today; facilities, public transport and susceptibility
indicators **missing**. With **Show** "all municipalities", **M-B** and **M-C** also have base
layers (they are A's buffer) but stay "not started"; **M-D** is all missing.

## D. Facilities of A: errors, personal data, extension

Sign in as `demo-analyst` / `demo-analyst-pass` in the second window for steps 13–15.

**13.** As `demo-analyst`: **Facilities** → choose **M-A**. Under **Import facilities of M-A**
choose `facilities-M-A-errors.csv`, type `Synthetic municipal register` in **Source of the
data**, click **Check the file**. ☐

*Expected:* **Changeset 1 (M-A)**, "pending · file import · facilities-M-A-errors.csv · by
demo-analyst", "3 added, 0 updated, 0 closed; 4 error(s).", and under **Errors (4)**:
"Row 2: name is required.", "Row 3: unknown service S-XX.", "Row 4: throughput unit visit does
not match the unit of S-SD (appointment).", "Row 5: the point is outside municipality M-A."
There is no **Approve** button for the analyst: "Waiting for an administrator to approve or
reject it."

**14.** As `demo-admin`: **Facilities** → **M-A** → in **Changesets** open **Changeset 1
(M-A)**, type `errors in the file` as comment and click **Reject**. ☐

*Expected:* "rejected by demo-admin · errors in the file". **Approve** is greyed out while the
report has errors.

**15.** As `demo-analyst`: upload `facilities-M-A-personal.csv` the same way. ☐

*Expected:* "3 added, 0 updated, 0 closed; 0 error(s)." and **Warnings (3)**: "Column
contact_person looks like personal data and was dropped (facilities are organisations, not
people).", the same for column **mobile**, and "Row 2, public_phone: looks like personal contact
data and was dropped; …". The preview lists three **added** facilities "(new id on approval)":
Community centre 1, Service desk 2, Care office 3 (fictional). Neither the name "Maria Example"
nor any `69…` number appears anywhere on the page.

**16.** Click **Download (CSV)** of the report and open it in a spreadsheet program. ☐

*Expected:* columns `severity, row, column, code, message`; three warning rows. No cell is run as
a formula.

**17.** As `demo-admin`: open that changeset (**Changeset 2**), comment `first import`,
**Approve**. ☐

*Expected:* "approved by demo-admin". The preview now shows ids **HF-000001**, **HF-000002**,
**HF-000003**. The facility list of M-A shows them "open since" today, quality "verified by the
municipality". **Onboarding** → M-A: "facilities in progress"; its status history has a second
row "base data ready → facilities in progress" (note "first approved facility changeset 2").

**18.** As `demo-analyst`: upload `facilities-M-A-update.csv`. ☐

*Expected:* **Changeset 3**: "1 added, 1 updated, 0 closed; 0 error(s)." The preview shows
**updated HF-000002** with exactly two changed fields, `notes` (— → "Throughput corrected by the
municipality (100 -> 90).") and `services.S-SD.throughput` (100 → 90), and one **added** "Day
centre 5 (fictional)", quality estimated, spatial unit A5.

**19.** As `demo-admin`: approve changeset 3, then click **HF-000002** in the facility list. ☐

*Expected:* the new facility is **HF-000004**. The page **Facility HF-000002** shows its
**History**: "added in changeset 2, by demo-analyst, approved by demo-admin …" and "updated in
changeset 3, …" with `notes, services.S-SD.throughput`, source "Synthetic municipal register".

**20.** On the **Facilities** page of M-A, download **Current facilities in the template** as
XLSX and open it. ☐

*Expected:* one sheet `facilities` with the template columns and five rows (HF-000001 has two
services), each with its `facility_id`. Download the **XLSX template** too: it has a sheet
`instructions` with the columns explained in English and Greek, including the rule on personal
data.

## E. Publish the package of study area A

**21.** As `demo-admin`: **Study areas and packages** → **New study area**: id `study-area-a`,
name `Study area A (fictional)`, core municipality **M-A**, buffer rule "hub default", click
**Create study area**. ☐

*Expected:* the card **Study area A (fictional) (study-area-a)**: "core: M-A · buffer: M-B,
M-C (whole neighbouring municipalities)", "not published yet", "Next version: 1.0.0 (first
version)". **Update available** says "No study area has changes since its last package."

**22.** Click **Publish 1.0.0**. ☐

*Expected:* a progress bar until **succeeded**, then **Package versions** lists **1.0.0**
"published" with today's date, a SHA-256 and **Download 1.0.0 (.zip)**. **Onboarding**: M-A is
now "published".

**23.** Click **Publish** again? There is no publish button any more; check it in the terminal:

```bash
curl -s -c /tmp/sn-hub -H 'Content-Type: application/json' -d '{"username":"demo-admin","password":"demo-admin-pass"}' http://127.0.0.1:8180/api/auth/login > /dev/null
curl -s -b /tmp/sn-hub -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:8180/api/hub/study-areas/study-area-a/publish
```

☐ *Expected:* `{"detail":"nothing changed for study-area-a since version 1.0.0; there is nothing to publish"}`.

## F. Onboard neighbour B and propagate

**24.** **Onboarding** → **Start onboarding of M-B**, follow it until **succeeded**. ☐

*Expected:* M-B "base data ready"; its report says "M-B: 8 feature(s) added, 0 changed, 0
closed." (municipality D, its two units and nodes and three edges: A's and B's features already
existed and were reused). **Study areas and packages**: study-area-a is still "up to date"
(nothing of A's package changed).

**25.** As `demo-analyst`: **Facilities** → **M-B**, upload `facilities-M-B.csv`; as
`demo-admin`, approve it (**Changeset 4**). ☐

*Expected:* one added facility, **HF-000005** (Community centre 4, verified by the
municipality).

**26.** As `demo-admin`: **Study areas and packages**. ☐

*Expected:* **Update available** lists "study-area-a: 1.0.0 → 1.1.0" with the draft changelog
"facilities added: HF-000005; coverage M-B/facilities: missing -> verified_by_municipality;
Changeset 4 (M-B): 1 added, 0 updated, 0 closed." The card says "update available" and "Next
version: 1.1.0 (additions or updates)".

**27.** Click **Publish 1.1.0** and wait for **succeeded**. ☐

*Expected:* **Package versions** lists 1.1.0 and 1.0.0; **Update available** is empty again.

**28.** Click **Coverage** (all municipalities). ☐

*Expected:* M-A "published", facilities **estimated** (the day centre is estimated: the worst
quality counts), "version changeset 3"; M-B "facilities in progress", facilities **verified by
the municipality**, "version changeset 4"; M-C and M-D "not started", facilities **missing**; M-D
has base layers now (B's buffer). Switch **Language** to Ελληνικά: the matrix reads «Πίνακας
κάλυψης», «λείπει», «επαληθευμένο από τον δήμο», «ανοιχτά δεδομένα».

## G. Import the packages in the municipal installation

**29.** Export both versions from the hub:

```bash
make hub-export-package STUDY_AREA=study-area-a VERSION=1.0.0 OUT=hub-exports
make hub-export-package STUDY_AREA=study-area-a VERSION=1.1.0 OUT=hub-exports
```

☐ *Expected:* "wrote hub-exports/study-area-a-1.0.0.zip (import it with: make import-package
PKG=…)" and the same for 1.1.0. (Downloading them with **Download … (.zip)** on the hub gives
the same files.)

**30.** Import 1.0.0 into the municipal installation with the existing command:

```bash
make import-package PKG=hub-exports/study-area-a-1.0.0.zip COMPOSE="podman compose -p solidaritynode-uat-municipality" FRONTEND_HOST_PORT=8280 BACKEND_HOST_PORT=8200 DB_HOST_PORT=5434
```

Type `yes` when asked. ☐

*Expected:* the preview "Package study-area-a 1.0.0 (schema 2.1)", "Active data: none",
"Status: new", added: municipalities 3, spatial_units 10 (A1–A6, B1, B2, C1, C2), facilities 4
(HF-000001 … HF-000004), network_nodes 14, network_edges 15 (E01–E15); then "Imported as data
version 1 (now active)." and a baseline run id.

**31.** Open <http://127.0.0.1:8280>, sign in as `demo-admin`. ☐

*Expected:* **Study area**: "Data package study-area-a, version 1.0.0 (…). Synthetic data." and
the orange "Edge-effect warning for units **A3, A4, A5, A6** …": B and C have no facility data
in 1.0.0.

**32.** In the municipal installation: **Admin** → **Or upload a package archive** → choose
`hub-exports/study-area-a-1.1.0.zip`. ☐

*Expected:* "Preview of study-area-a 1.1.0": update, compared with active 1.0.0, schema 2.1;
**facilities added HF-000005**; nothing changed or closed in the other layers; "Coverage
changes: M-B / facilities: missing → verified by the municipality"; changelog 1.0.0 and 1.1.0;
no problem in red.

**33.** Click **Confirm import**. ☐

*Expected:* "Imported as data version 2; it is now active." On **Study area** the warning now
names only **A4, A5** (next to C, still without facilities): the warning **disappeared for A3
and A6**, the units next to B. The coverage table shows M-B facilities "verified by the
municipality". The footer shows "data study-area-a 1.1.0" and a **User guide** link.

**34.** **Scenarios** → **Baseline (no changes)**. ☐

*Expected:* its latest run on 1.1.0 is **succeeded** (queued by the import).

## H. Permissions and the proxy

**35.** As `demo-analyst` on the hub: **Study areas and packages** and **Sources**. ☐

*Expected:* no **Publish**, **Create study area** or **Register a source** controls. Through the
proxy, the analyst is refused:

```bash
curl -s -c /tmp/sn-an -H 'Content-Type: application/json' -d '{"username":"demo-analyst","password":"demo-analyst-pass"}' http://127.0.0.1:8180/api/auth/login > /dev/null
curl -s -o /dev/null -w '%{http_code}\n' -b /tmp/sn-an -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:8180/api/hub/study-areas/study-area-a/publish
```

☐ *Expected:* `403`.

**36.** The municipal installation has no hub routes:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8280/api/hub/status
```

☐ *Expected:* `404`.

## I. Finish

**37.** Stop the UAT stacks (their volumes are kept until the next `make uat-hub`):

```bash
make hub-down
podman compose -p solidaritynode-uat-municipality down
```

☐ *Expected:* the containers are removed; `make up` (port 8080) was never touched.
