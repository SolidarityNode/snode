# 0001. Monorepo with core, backend, frontend

- Status: Accepted
- Date: 2026-11-24
- Related: AGENTS.md "Architecture rules"

## Context

SolidarityNode has a modelling library, an API and a web UI that change together while the method is being designed. Contributors include researchers who mainly touch the specs and `core`. Specs, code and decisions must stay cross-referenced.

## Options

1. **Monorepo** (`core/`, `backend/`, `frontend/`, `docs/`, `.github/`): one PR can change spec, model and API together; one CI; one issue tracker.
2. **Separate repositories** per component: clearer ownership and independent releases, but cross-cutting changes need coordinated PRs and the spec drifts from the code.

## Decision

Use a monorepo. `core` is a standalone Python package (`solidaritynode-core`) that the backend consumes through a local path dependency. Dependency direction is `backend → core`; `core` never imports `backend`, `frontend`, web frameworks or database drivers.

## Consequences

- CI workflows use `paths` filters so a change only runs the affected component.
- The `core` independence rule is enforced by tests and a lint rule, so `core` can be split into its own repository later without changes.
- Each component keeps its own lockfile (`core/uv.lock`, `backend/uv.lock`, `frontend/pnpm-lock.yaml`).
