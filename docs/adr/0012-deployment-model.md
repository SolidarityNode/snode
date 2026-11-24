# 0012. Deployment model: municipal installations and a hub

- Status: Accepted for v0.1, to be revisited
- Date: 2026-11-24 (accepted for v0.1: 2026-11-25)
- Related: Spec 00 §3 (Deployment, Onboarding, Data package), OQ-21, OQ-28; ADR 0013, 0014, 0015

## Context

Spec 00 §3 describes one codebase running in two roles: a **municipal installation** (one per study area, with its own users, scenarios, runs and tickets) and a **hub** (national raw sources, onboarding, curated data, data packages, optional aggregated indicators shared upwards). Tickets and operational data must stay inside the municipality (AGENTS.md privacy rules, OQ-21). Everything must keep running locally with `make up` (Podman default, Docker supported).

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

- In this version only the **municipal installation** works fully: one study area, its own
  users, scenarios and runs, data obtained by **manual import** of package files (works offline).
- `hub` starts the same services but offers no hub features yet (onboarding is the next PR).
- `GET /config` exposes the mode so the UI and testers can see it.

**Why:** the simplest option that keeps both roles in one image and leaves the hub open.

## Consequences

- Routers and UI sections will be enabled per role when hub features exist.
- Pulling packages from the hub, upward flow (ADR 0014) and multi-tenancy are not implemented.
