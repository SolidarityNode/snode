# CLAUDE.md

Guidance for Claude Code (and any contributor) working in this repository.

## Project

SolidarityNode is an open-source spatial probabilistic framework for estimating accessibility, latent social need, social vulnerability and resilience of social service networks (healthcare, social care and other public services). It uses Bayesian Networks (BN), Dynamic Bayesian Networks (DBN) and spatial/network analysis. It is research software in early development.

Source of truth for the science: `docs/specs/` (research description and per-module specs). If code and spec disagree, stop and flag it; do not silently pick one.

## Domain invariants (never violate)

1. **Unit of analysis** is `spatial unit × social group × service × time`. Core data structures and outputs are indexed by these four dimensions.
2. **Vulnerability is not resilience, and not risk.** Vulnerability is the relationship that turns a disruption (group exposure, service loss) into consequences for a group given its social susceptibility; in code it is the CPT `P(V | GE, SL, SS)`, evaluated at scenarios (Paper 3) or at observed disruptions (Paper 4), and learned from data as parameters (OQ-16). Resilience = dynamic property derived from the loss-and-recovery trajectory. Risk = vulnerability weighted by disruption probabilities. Separate modules, separate outputs. Never define resilience as just the inverse of recovery time, and never let vulnerability results depend on which scenarios a run includes.
3. **Facility state is not population service loss.** A degraded facility does not imply lost coverage for a spatial unit if alternatives exist. Coverage is computed at the network level.
4. **Observed demand is not need.** Latent need is estimated explicitly; keep observed demand and estimated need as distinct quantities. Hidden need (never expressed), unmet expressed need (requests not fulfilled) and met need never overlap; take-up means expressing need, not being served (OQ-8).
5. **Social group is not social susceptibility.** The group says who is being examined; susceptibility is the probability that the group faces increased difficulty under given conditions.
6. **Outputs carry uncertainty.** Prefer distributions or intervals to point estimates. Never collapse uncertainty silently.
7. **Operational support is a system response**, not an independent resilience measure.
8. **Digital Twin is a future direction**, not an assumption. Do not build twin-specific machinery yet.
9. **Keep variable kinds distinct.** BN nodes, computed simulation variables and scenario parameters are different things (see `docs/specs/00-domain-model.md`, section 4). Do not turn one into another without an ADR.
10. **Decisions feed the papers.** When a ticket or ADR changes the method, update `docs/specs/paper-revisions.md` (what changes in which paper section, and why) in the same PR.
11. **Open questions are not yours to resolve.** `docs/specs/open-questions.md` lists what the papers leave unspecified. Implement only what a spec states; reference `OQ-n` in code and tickets; if a ticket needs an unresolved answer, stop and comment on the issue.

## Architecture rules

- Monorepo: `core/` (Python library), `backend/` (API), `frontend/` (web UI), `docs/`, `.github/`.
- Dependency direction: `backend → core`. `core` MUST NOT import from `backend` or `frontend`, and MUST NOT depend on web frameworks or a database driver.
- `core` modules (map in `docs/specs/00-domain-model.md`): `model`, `bayes`, `accessibility`, `demand`, `capacity`, `service_gap`, `latent_need`, `scenarios`, `vulnerability`, `operations`, `dynamics`, `resilience`, `uncertainty`, `sensitivity`, `validation`. Each exposes a small typed public API; internals are private.
- Long-running simulations run as background jobs, never inside a request handler.
- Large datasets live in files (Parquet), metadata and results indexes in PostgreSQL/PostGIS.
- Significant decisions are recorded as short ADRs in `docs/adr/`.

## Stack (initial choices; change via ADR)

- Python 3.12, `uv` for environments, `ruff` (lint + format), `mypy` (strict in `core`), `pytest`.
- Backend: FastAPI, Pydantic v2, SQLAlchemy + Alembic, PostgreSQL with PostGIS.
- Core: NumPy, pandas, GeoPandas, NetworkX/OSMnx for network analysis, pgmpy (BN/DBN; evaluate limits via ADR before committing).
- Frontend: React + TypeScript (strict), Vite, `pnpm`, Vitest, ESLint, Prettier. Map library chosen via ADR.
- Containers: Podman (rootless) is the default engine; Docker must keep working. The engine and compose command are set once in the Makefile (`CONTAINER_ENGINE ?= podman`, `COMPOSE ?= podman compose`) and are overridable from the environment. Never hard-code `docker` in scripts, docs or CI; call the Makefile variables instead. Compose files follow the Compose spec (`compose.yaml`) and images use fully qualified names (for example `docker.io/postgis/postgis:...`), since Podman requires them. Avoid privileged ports (<1024) and rootful-only features. Everything runs locally with `make up`.

## Commands

Requires `uv`, Node.js 26 with `pnpm` 12, and Podman (or Docker). `make help` lists all targets.

- `make setup` — install locked dependencies (`uv sync --locked` in `core/` and `backend/`, `pnpm install --frozen-lockfile` in `frontend/`)
- `make lint` — ruff check, ruff format --check and mypy (strict) for core and backend; eslint, prettier --check and `tsc` for frontend
- `make test` — pytest (core, backend) and Vitest (frontend)
- `make fmt` — ruff fix/format, prettier, eslint --fix
- `make up` / `make down` — start/stop db, backend and frontend with `$(COMPOSE)` (default `podman compose`); frontend http://localhost:8080, backend http://localhost:8000
- `make logs`, `make ps` — follow logs, show containers
- `make images` — build images with `$(CONTAINER_ENGINE)`
- `make licenses` — fail on dependency licences incompatible with AGPL-3.0
- `make labels` — create GitHub labels from `.github/labels.yml` (needs `gh auth login`)
- `make clean` / `make distclean` — remove caches and build output / also virtualenvs and node_modules
- Per component: `make lint-core`, `test-core`, `lint-backend`, `test-backend`, `lint-frontend`, `test-frontend`
- Docker instead of Podman: `CONTAINER_ENGINE=docker COMPOSE="docker compose" make up`

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
- **Every processed dataset has a processing note** in `docs/data-processing/` (`DP-NNN`, from `TEMPLATE.md`), with exact steps, versions and checks. Reusable processing lives in `data-processing/qgis/` (Processing models, scripts, projects with relative paths). When code or a ticket changes how data are prepared, update or add the note in the same PR. QGIS is a tool for preparing data, never a runtime dependency of `core` or `backend`.

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
