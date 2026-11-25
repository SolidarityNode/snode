# Changelog

All notable changes are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project will use [Semantic Versioning](https://semver.org/) once releases start.

## [Unreleased]

### Added

- Platform mechanics (no scientific method): data packages (ADR 0013) with validation, checksums, preview of changes and transactional import of versioned data; demo packages 1.0.0 and 1.1.0 (DP-002); edge-effect warnings for core units next to buffer municipalities without facility data (OQ-28, warning only).
- `DEPLOYMENT_MODE` (`municipality` | `hub`; ADR 0012). Only the municipal installation is complete.
- Local accounts with Argon2id, sessions, roles admin, analyst and viewer (ADR 0015); `make create-admin`; demo users in development.
- Versioned scenario overlays with a JSON Schema (`docs/schemas/scenario.schema.json`, ADR 0016); create, list, get, new version, duplicate, soft delete, validate, revalidate.
- Runs with input hash and cached reuse, a PostgreSQL job queue and a `worker` service with progress, cancel, a heartbeat lease that lets any worker fail a dead worker's jobs, and an optional maximum runtime per job kind (ADR 0006, 0017); every result value stores mean, median and configurable interval quantiles computed from the samples, and totals come from samples (ADR 0017); samples are joint Monte Carlo draws (`diagnostic-v0` 0.2.0) stored in Parquet with run metadata, a SHA-256 checked on read and export, a compact sorted zstd layout and a size estimate with a warning before each run (ADR 0008); results in PostGIS, samples in Parquet (ADR 0008); comparison with the baseline; CSV and GeoPackage export with reproducibility metadata.
- Core: model registry, scenario overlay and the diagnostic model `diagnostic-v0` (labelled "Diagnostic model: not a research result").
- Frontend: login, study area, scenarios, scenario editor, run, compare and admin screens with Leaflet (ADR 0007), English and Greek, generated API types; Playwright end-to-end test. Results maps: values with intervals everywhere, an optional uncertainty map (interval width), a fixed 0–1 scale for probabilities, one shared scale on comparison screens, and the data-quality layer as a toggle.
- Tickets record `facility_id` (OQ-29); nothing is stored yet (ADR 0010).
- Monorepo skeleton: `core/`, `backend/`, `frontend/`, `docs/`, `data/synthetic/`, `.github/`, Makefile.
- `core`: typed domain model (OQ-1 notation, entities, anonymous `Ticket`, recording coverage, recovery trajectories, `IndexedValues` container, uncertain values, Low/Medium/High states, service-unit quantities, variable catalogue) and typed interfaces for every module. No scientific method implemented.
- `backend`: FastAPI app with `/health`, `/health/ready`, `/version`; settings; SQLAlchemy and Alembic wired to PostGIS; placeholder routers; anonymous ticket schema; background job interface.
- `frontend`: Vite + React + TypeScript shell with a health page.
- Containers: `compose.yaml` (PostGIS, backend, frontend), Podman by default, Docker supported.
- CI: per-component workflows, DCO check, image builds with Podman and Docker, licence check, Dependabot.
- Governance and docs: contributing guide, code of conduct, security and trademark policies, architecture, ADRs 0001–0011.
- Scenario what-if intervention placeholders (`CapacityChange`, `NewFacility`; Paper 1 §13), no behaviour.
- `APP_ENV` (`development` | `test` | `production`); the backend refuses `change-me` secrets outside development and test, and never echoes setting inputs in errors.
- `/version` returns the git commit and `APP_ENV`; the frontend footer shows them.
- Synthetic demo dataset (`data/synthetic/demo/`, DP-001): two fictional municipalities, GeoPackage + CSV, hand-check travel times, one reference disruption scenario; generator `scripts/generate_demo_data.py`.
- Temporary database schema `demo` (migration 0002) and `make seed` loader; to be replaced by data-package import.
- Make targets `env`, `check-config`, `wait`, `stop`, `db-shell`, `seed`, `reset`, `uat`; `make setup` checks tools and creates `.env`.
- UAT: `docs/uat/README.md`, `docs/uat/00-bootstrap.md`, "How to test (UAT)" in the PR template, "Acceptance test (UAT)" in feature tickets, labels `uat` and `uat-failed`.
- ADR stubs 0012–0017: deployment model, data packages, upward data flow, authentication and roles, scenario schema and versioning, run reproducibility.
- `data-processing/` folders for QGIS models, scripts, projects and styles; `data/local/` and QGIS temporary files ignored.

### Changed

- The temporary `demo` schema is dropped (migration 0003); `make seed` imports demo package 1.0.0. The job interface takes a kind and JSON payload and supports cancel; the in-process runner is removed.
- CI: the DCO check exempts Dependabot commits; Dependabot no longer proposes TypeScript major updates until typescript-eslint supports TypeScript 7.
- Agent instructions moved to the open `AGENTS.md` convention: root `AGENTS.md` (former `CLAUDE.md` content) plus area files for `core/`, `backend/`, `frontend/` and `data-processing/`, human-readable versions in `docs/conventions/`, `CLAUDE.md` files reduced to import bridges, and a Claude Code `/add-rule` command.
- `SOLIDARITYNODE_ENVIRONMENT` replaced by `APP_ENV`; `.env.example` placeholders are plain `change-me`, with a comment per setting.
- Ports and URLs use `127.0.0.1`.
