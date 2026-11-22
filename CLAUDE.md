# CLAUDE.md

Guidance for Claude Code (and any contributor) working in this repository.

## Project

SolidarityNode is an open-source spatial probabilistic framework for estimating accessibility, latent social need, social vulnerability and resilience of social service networks (healthcare, social care and other public services). It uses Bayesian Networks (BN), Dynamic Bayesian Networks (DBN) and spatial/network analysis. It is research software in early development.

Source of truth for the science: `docs/specs/` (research description and per-module specs). If code and spec disagree, stop and flag it; do not silently pick one.

## Domain invariants (never violate)

1. **Unit of analysis** is `spatial unit × social group × service × time`. Core data structures and outputs are indexed by these four dimensions.
2. **Vulnerability is not resilience.** Vulnerability = predisposition to adverse effects given exposure, service loss and social susceptibility. Resilience = dynamic property derived from the loss-and-recovery trajectory. Separate modules, separate outputs. Never define resilience as just the inverse of recovery time.
3. **Facility state is not population service loss.** A degraded facility does not imply lost coverage for a spatial unit if alternatives exist. Coverage is computed at the network level.
4. **Observed demand is not need.** Latent need is estimated explicitly; keep observed demand and estimated need as distinct quantities.
5. **Social group is not social susceptibility.** The group says who is being examined; susceptibility is the probability that the group faces increased difficulty under given conditions.
6. **Outputs carry uncertainty.** Prefer distributions or intervals to point estimates. Never collapse uncertainty silently.
7. **Operational support is a system response**, not an independent resilience measure.
8. **Digital Twin is a future direction**, not an assumption. Do not build twin-specific machinery yet.

## Architecture rules

- Monorepo: `core/` (Python library), `backend/` (API), `frontend/` (web UI), `docs/`, `.github/`.
- Dependency direction: `backend → core`. `core` MUST NOT import from `backend` or `frontend`, and MUST NOT depend on web frameworks or a database driver.
- `core` modules: `accessibility`, `latent_need`, `vulnerability`, `operations`, `dynamics`, `resilience`, `validation`. Each exposes a small typed public API; internals are private.
- Long-running simulations run as background jobs, never inside a request handler.
- Large datasets live in files (Parquet), metadata and results indexes in PostgreSQL/PostGIS.
- Significant decisions are recorded as short ADRs in `docs/adr/`.

## Stack (initial choices; change via ADR)

- Python 3.12, `uv` for environments, `ruff` (lint + format), `mypy` (strict in `core`), `pytest`.
- Backend: FastAPI, Pydantic v2, SQLAlchemy + Alembic, PostgreSQL with PostGIS.
- Core: NumPy, pandas, GeoPandas, NetworkX/OSMnx for network analysis, pgmpy (BN/DBN; evaluate limits via ADR before committing).
- Frontend: React + TypeScript (strict), Vite, `pnpm`, Vitest, ESLint, Prettier. Map library chosen via ADR.
- Everything runs locally with `docker compose up`.

## Commands

Fill in exact commands once the bootstrap PR is merged. Expected targets:

- `make setup` — install all dependencies
- `make test` — run all tests (core, backend, frontend)
- `make lint` — ruff, mypy, eslint, prettier check
- `make fmt` — auto-format
- `make up` — `docker compose up`

Run `make lint test` before every commit. Do not mark work done if either fails.

## Conventions

- Type hints everywhere in Python; no untyped public functions.
- Small, pure, testable functions in `core`. Randomness goes through an explicit seed/`numpy.random.Generator` argument.
- Every public function in `core` has a docstring stating its inputs, outputs, units and the spec section it implements (for example `Spec §3.1`).
- Tests live next to the code's package in `tests/`. Use synthetic fixtures only.
- Commits: Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`), signed off with `git commit -s` (DCO).
- Branches: `feat/<issue-number>-short-name`. One ticket, one branch, one PR. Reference the issue in the PR (`Closes #N`).

## Data and privacy rules

- **Never commit real personal or operational data.** Only synthetic data under `core/tests/fixtures/` and `data/synthetic/`.
- The request-logging mechanism must be anonymous by design: store only spatial unit of origin, social group, service type and timestamps. No names, contact details, exact addresses or device identifiers.
- No secrets in the repo. Use `.env` (gitignored) and keep `.env.example` current.
- Third-party data (for example OpenStreetMap) must be attributed and its license respected; record sources in `docs/data-sources.md`.

## Licensing

- Project license: AGPL-3.0. New dependencies must have AGPL-compatible licenses (MIT, BSD, Apache-2.0 are fine; no GPL-incompatible or proprietary-only dependencies). State the license of any new dependency in the PR description.

## Workflow for tickets

1. Read the issue fully, including acceptance criteria and the linked spec section.
2. If anything is ambiguous or the spec is silent, do not invent methodology: comment on the issue with the question and stop.
3. Plan briefly, implement in small commits, add tests that cover each acceptance criterion.
4. Update docs and the spec cross-reference if behaviour changed.
5. Run `make lint test`, then open a PR using the template. Do not merge your own PR.

## Definition of done

- All acceptance criteria met and covered by tests.
- Lint, type check and tests pass locally and in CI.
- Public API documented; relevant `docs/` updated.
- No real data, no secrets, no new dependency without a license check.
- Domain invariants above still hold.
