# 0012. Deployment model: municipal installations and a hub

- Status: Accepted for v0.1, to be revisited
- Date: 2026-11-24 (accepted for v0.1: 2026-11-25)
- Related: Spec 00 §3 (Deployment, Onboarding, Data package), OQ-21, OQ-28; ADR 0013, 0014, 0015

## Context

Spec 00 §3 describes one codebase running in two roles: a **municipal installation** (it serves one study area of one or more core municipalities, with its own users, scenarios, runs and tickets) and a **hub** (national raw sources, onboarding, curated data, data packages, optional aggregated indicators shared upwards). Tickets and operational data must stay inside the municipality (AGENTS.md privacy rules, OQ-21). Everything must keep running locally with `make up` (Podman default, Docker supported).

## Options to evaluate

1. **One codebase, role chosen by configuration** (for example `APP_ROLE=municipality | hub`): routers, jobs and UI sections enabled per role; one image.
2. **Separate hub service** in the same monorepo sharing `core`, with its own backend and database.
3. **Single multi-tenant installation** hosting several municipalities. Simpler to operate, but weakens the "tickets never leave the municipality" property and the privacy boundary of OQ-21.

## Questions to answer before deciding

- Which features exist only in the hub (raw sources, onboarding, package publishing) and which only in installations (tickets, local runs)?
- How does an installation obtain packages (pull from the hub, manual import of a file)? Must it work offline?
- Who operates installations (municipal IT, a regional body, the project)? What are the minimum hardware requirements?
- How is the role reflected in `/version` and the UI so testers know which role they are using?

## Decision

**Accepted for v0.1, to be revisited: option 1, one codebase, role chosen by configuration**,
with the setting `DEPLOYMENT_MODE=municipality | hub` (default `municipality`).

- An installation serves **one study area of one or more core municipalities** (plus its buffer,
  OQ-28). In this version only the **municipal installation** works fully: its own users,
  scenarios and runs, data obtained by **manual import** of package files (works offline).
- `hub` starts the same services but offers no hub features yet (onboarding is the next PR).
- `GET /config` exposes the mode so the UI and testers can see it.
- **Role lock.** The role is stored in the database (table `installation`, one row) when it is
  first initialised (migration 0007, from `DEPLOYMENT_MODE`). The API, the worker and the CLI
  refuse to start when `DEPLOYMENT_MODE` differs from it, with a message naming both roles. One
  database serves one role; switching role means a new database
  (`backend/tests/test_roles.py`).
- **Role separation.** Routers of the other role are **not mounted** (not merely disabled):
  their paths answer 404 and are absent from the OpenAPI schema. Ticket routes (`/requests`)
  exist only in `municipality`, hub routes (`/hub`) only in `hub`; each has one read-only status
  endpoint for now. Tables of one role are created only by migrations guarded by the stored role
  (`services.installation.stored_role`), so ticket tables never exist in the hub; none exist yet
  (ADR 0010). The exported `docs/schemas/openapi.json` describes the municipal installation.

**Why:** the simplest option that keeps both roles in one image and leaves the hub open.

### Hub (v0.2, accepted for v0.2, to be revisited)

- The hub runs as **its own compose project** with its own database and volumes (`make hub-up`,
  `make uat-hub`): the role lock forbids sharing a database with an installation. Hub tables
  are created by migration 0011 only when the stored role is `hub`; `openapi-hub.json` describes
  the hub API (`openapi.json` stays the municipal installation's).
- Raw sources, uploaded facility files and published packages live in the `hub` volume
  (`SOLIDARITYNODE_HUB_STORAGE_DIR`). Geoprocessing uses PostGIS in the hub database; QGIS is
  not a runtime dependency.
- **Roles in the hub** reuse ADR 0015's: `viewer` reads everything; `analyst` uploads facility
  files and proposes manual edits (pending changesets); `admin` registers sources, runs the base
  step, changes onboarding status, approves or rejects changesets, creates study areas and
  publishes packages, and manages users. A dedicated "hub operator" role was not needed.
- The UI shows hub screens (and a "hub" badge) when `/config` says `hub`; the footer of both
  roles links to the user guide of the running version (`SOLIDARITYNODE_DOCS_BASE_URL`).

## Consequences

- UI sections are enabled per role (hub screens since v0.2).
- Pulling packages from the hub, upward flow (ADR 0014) and multi-tenancy are not implemented.
- **Commitment for any future connection (not implemented now).** Every connection between an
  installation and the hub is **initiated by the installation** (outbound only): it pulls
  packages and, if ADR 0014 allows, pushes what it chose to share. The hub never connects into
  an installation, needs no inbound access to it and holds no credentials for it. The
  municipality controls **what** is sent and **when**; nothing leaves an installation without
  that decision.

### Open questions (kept open)

- **Operator**: who runs installations (municipal IT, a regional body, the project) and the hub.
- **Minimum hardware** for an installation and for the hub.
- **Update policy**: who updates installations, how often, and how database migrations and
  data packages are rolled out.
- **Public exposure**: how an installation is reached from outside its machine (reverse proxy
  with HTTPS, certificates, which ports). Today everything binds to 127.0.0.1.

These belong to a future **"production operations"** ADR (together with backups of the database
and the results volume, ADR 0008).
