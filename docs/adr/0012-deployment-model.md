# 0012. Deployment model: municipal installations and a hub

- Status: Proposed (stub, needs a human decision)
- Date: 2026-11-24
- Related: Spec 00 §3 (Deployment, Onboarding, Data package), OQ-21, OQ-28; ADR 0013, 0014, 0015

## Context

Spec 00 §3 describes one codebase running in two roles: a **municipal installation** (one per study area, with its own users, scenarios, runs and tickets) and a **hub** (national raw sources, onboarding, curated data, data packages, optional aggregated indicators shared upwards). Tickets and operational data must stay inside the municipality (CLAUDE.md privacy rules, OQ-21). Everything must keep running locally with `make up` (Podman default, Docker supported).

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

Not decided.

## Consequences

To be written. Until decided, the bootstrap runs a single local installation with no role switch.
