# Contributing to SolidarityNode

Thank you for your interest. SolidarityNode is early-stage research software: code, methodological review, documentation and synthetic test data are all welcome.

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md). Report security issues privately as described in [SECURITY.md](SECURITY.md).

## Before you start

Read, in this order:

1. [`AGENTS.md`](AGENTS.md): domain invariants, architecture rules and conventions. They apply to every contributor, human or AI (Claude Code, Codex, Cursor and other coding agents all read this file).
   - Also read the `AGENTS.md` of the folder you work in ([`core/`](core/AGENTS.md), [`backend/`](backend/AGENTS.md), [`frontend/`](frontend/AGENTS.md), [`data-processing/`](data-processing/AGENTS.md)). The root file always applies; if the two conflict, the root wins and the conflict should be reported.
   - The same area rules with short explanations and examples are in [`docs/conventions/`](docs/conventions/README.md).
   - `CLAUDE.md` files only import `AGENTS.md` for Claude Code; they never contain rules.
2. [`docs/specs/README.md`](docs/specs/README.md): how the specification is organised.
3. [`docs/specs/00-domain-model.md`](docs/specs/00-domain-model.md) and [`docs/specs/open-questions.md`](docs/specs/open-questions.md).
4. [`docs/architecture.md`](docs/architecture.md).

## Development setup

Requirements: `git`, `make`, [`uv`](https://docs.astral.sh/uv/), Node.js 26 with [`pnpm`](https://pnpm.io/) 12, and Podman (default) or Docker for the full stack.

```bash
make setup        # check tools, create .env if missing, install locked dependencies
make test-db      # once per session: PostGIS for the backend tests (or keep `make up` running)
make lint test    # must pass before every commit (unit and integration tests, no containers)
make test-e2e     # end-to-end test in a throw-away stack; also runs in CI on every PR
make up           # start db, backend and frontend (Podman by default)
make down
```

`make setup` names any missing tool (`uv`, `node`, `pnpm`); install it and open a new login shell so it is on `PATH`. No manual editing of `.env` is needed for development.

With Docker instead of Podman:

```bash
CONTAINER_ENGINE=docker COMPOSE="docker compose" make up
```

`make help` lists all targets. Optional local hooks: `uvx pre-commit install`.

## Configuration

All configuration comes from `.env` (git-ignored), created by `make setup` from [`.env.example`](.env.example). `make setup` also warns when `.env` lacks a key that `.env.example` defines. Defaults are safe for local development; secrets are `change-me` placeholders, which the backend **refuses** when `APP_ENV` is anything other than `development` or `test` (check with `make check-config APP_ENV=production`). Production values are never committed.

| Setting | Used by | Default | Meaning |
| --- | --- | --- | --- |
| `POSTGRES_DB` | db, backend | `solidaritynode` | Database name |
| `POSTGRES_USER` | db, backend | `solidaritynode` | Database user |
| `POSTGRES_PASSWORD` | db, backend | `change-me` | Database password (secret) |
| `DB_HOST_PORT` | compose | `5432` | Host port for PostgreSQL, bound to 127.0.0.1 |
| `BACKEND_HOST_PORT` | compose, Makefile | `8000` | Host port for the API, bound to 127.0.0.1 |
| `FRONTEND_HOST_PORT` | compose, Makefile | `8080` | Host port for the frontend, bound to 127.0.0.1 |
| `APP_ENV` | backend | `development` | `development`, `test` (test suite) or `production`; outside development and test, placeholder secrets are refused |
| `SOLIDARITYNODE_LOG_LEVEL` | backend | `info` | `debug`, `info`, `warning` or `error` |
| `SOLIDARITYNODE_DATABASE_URL` | backend on the host | built from `POSTGRES_*` in compose | SQLAlchemy URL (secret) |
| `SOLIDARITYNODE_CORS_ORIGINS` | backend | `["http://localhost:5173"]` | Origins allowed to call the API directly |
| `DEPLOYMENT_MODE` | backend | `municipality` | `municipality` or `hub` (ADR 0012); only the municipal installation is complete in v0.1 |
| `SOLIDARITYNODE_BASEMAP` | backend → frontend | `osm` | Map background: `osm` (OpenStreetMap tiles, attributed, needs internet) or `blank` (offline) |
| `SOLIDARITYNODE_DIAGNOSTIC_STEP_DELAY_S` | runs | `0.5` | Pause after each progress step so progress and cancel can be followed; recorded in the run configuration |
| `SOLIDARITYNODE_SESSION_HOURS` | backend | `12` | Login session lifetime |
| `SOLIDARITYNODE_SESSION_COOKIE_SECURE` | backend | `false` | Session cookie only over HTTPS (set `true` behind TLS) |
| `SOLIDARITYNODE_RESULTS_DIR` | backend, worker on the host | `var/results` (`/data/results` volume in compose) | Per-sample Parquet results and package uploads |
| `SOLIDARITYNODE_PACKAGES_DIR` | backend | `data/synthetic/packages` | Data packages offered for import on the Admin screen |
| `SOLIDARITYNODE_WORKER_NAME` | worker | `worker` | Worker name; on start it fails the runs it was running when it stopped |
| `SOLIDARITYNODE_TEST_DATABASE_URL` | backend tests | compose `db` on 127.0.0.1:5432 | PostGIS server on which the tests create a throw-away database |
| `GIT_COMMIT` | image builds | set by `make up` | Build identity shown by `/version` and the footer |
| `CONTAINER_ENGINE`, `COMPOSE` | Makefile | `podman`, `podman compose` | Container engine and compose command |

**Adding a setting:** add it to `.env.example` in the same PR with a safe development default (secrets as `change-me`) and a one-line comment, and add a row to this table (AGENTS.md, "Configuration").

## Testing by hand (UAT)

The maintainer tests every PR by hand before merging. `make uat` gives a fresh, seeded environment and prints the URLs to open; see [`docs/uat/README.md`](docs/uat/README.md). Every PR fills in the **"How to test (UAT)"** section of the template with numbered steps and expected results, and every feature ticket has an **"Acceptance test (UAT)"** section. Failed UAT is reported as a PR comment and the `uat-failed` label.

## Workflow

1. **One ticket, one branch, one PR.** Branch name: `feat/<issue-number>-short-name` (or `fix/…`, `docs/…`, `chore/…`).
2. Read the issue fully, including acceptance criteria and the linked spec section.
3. If anything is ambiguous or the spec is silent, **do not invent methodology**: comment on the issue with the question and stop (see below).
4. Implement in small commits and add tests that cover every acceptance criterion. Use synthetic data only.
5. Update docs and the spec cross-reference if behaviour changed.
6. Run `make lint test`, open a PR with the template and reference the issue (`Closes #N`). Do not merge your own PR.

### Commits and DCO sign-off

Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`), and sign off every commit:

```bash
git commit -s -m "feat(core): add travel time interface"
```

The sign-off certifies the [Developer Certificate of Origin](https://developercertificate.org/): you wrote the change or have the right to submit it under the project licence (AGPL-3.0). The `dco` CI check rejects PRs with unsigned commits. Commits by Dependabot are exempt, since it cannot sign off. To fix the last commit: `git commit --amend -s --no-edit`; for several: `git rebase --signoff main`.

### Pull requests

- Fill in every section of the PR template, including the acceptance-criteria checklist, the dependency/licence table and the data/privacy checklist.
- New dependencies must have an AGPL-compatible licence (MIT, BSD, Apache-2.0, ISC, MPL-2.0, LGPL, GPL-3.0, AGPL-3.0). The `licenses` CI check fails otherwise. State each new dependency's licence in the PR.
- CI runs only the workflows affected by your change (`core`, `backend`, `frontend`, `containers`, `licenses`, plus `dco`).

## Changing the rules

Rules live only in `AGENTS.md` files (root and area folders). To add, change or remove one:

1. Open an issue or a PR on a branch `docs/rule-<short-name>`, titled `docs(rules): <summary>`, and list each rule added, changed or removed.
2. Put the rule in the right file: the root `AGENTS.md` if it applies everywhere, otherwise the area `AGENTS.md`, in short imperative wording. Add the same rule with a one-line reason (and an example if useful) to `docs/conventions/<area>.md`.
3. If the rule can be enforced automatically (lint, type check, formatter, test, CI check), add that check instead or as well.
4. Point out any conflict or overlap with existing rules in the PR instead of silently overriding them. Rules that change the method or a technical choice need an ADR or a decision in `docs/specs/open-questions.md` first.

The full procedure is in "Maintaining these instructions" in [`AGENTS.md`](AGENTS.md). Claude Code users can run `/add-rule <area>: <rule>`, which follows it and asks for confirmation before editing.

## Proposing a method

Scientific methods (formulas, CPTs, thresholds, inference schemes) are **specification first, code second**:

1. Open a **Research question** issue (template provided) citing the paper section and the relevant `OQ-n`, if any.
2. Describe the options, their consequences, and references (verify every reference).
3. Once agreed, the decision is recorded in `docs/specs/open-questions.md` (status `decided`, with reasoning and rejected options), the paper changes in `docs/specs/paper-revisions.md`, and the model in `docs/specs/00-domain-model.md`. Technical choices go into an ADR under `docs/adr/`.
4. Only then is an implementation ticket opened, referencing the decision.

## How open questions are handled

- Open questions are listed in `docs/specs/open-questions.md` as `OQ-n` with status `open`, `partly decided` or `decided`.
- **Code never resolves an open question.** Where code touches one, it references `OQ-n` in a docstring and leaves the behaviour undefined (abstract interface or `NotImplementedError`).
- Tickets that depend on an open question carry the `needs-spec` label and wait for the decision.
- If you need a modelling decision to proceed, write an ADR stub (status `Proposed`) or a research question; do not encode the choice silently.

## Data and privacy

- Never commit real personal or operational data. Synthetic data only, under `core/tests/fixtures/` and `data/synthetic/`.
- Request tickets are anonymous by design: spatial unit of origin, social group, service, facility (OQ-29) and timestamps only (see OQ-21).
- No secrets in the repository. Use `.env` (gitignored) and keep `.env.example` current.
- Attribute third-party data and record it in [`docs/data-sources.md`](docs/data-sources.md).
- Real open data (OpenStreetMap, ELSTAT, DEM, GTFS) is downloaded to `data/local/` (git-ignored) by scripts, never committed.
- Every processed dataset has a processing note `DP-NNN` in [`docs/data-processing/`](docs/data-processing/README.md), copied from its `TEMPLATE.md`. Reusable QGIS models, scripts and projects go in `data-processing/qgis/`; QGIS is never a runtime dependency.
- The synthetic demo dataset (`data/synthetic/demo/`, DP-001) is generated by `scripts/generate_demo_data.py`; regenerate it rather than editing files by hand.

## Licence

By contributing you agree that your contributions are licensed under the [AGPL-3.0](LICENSE). The project name is covered by [TRADEMARK.md](TRADEMARK.md), not by the licence.
