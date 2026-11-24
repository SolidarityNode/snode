# Changelog

All notable changes are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project will use [Semantic Versioning](https://semver.org/) once releases start.

## [Unreleased]

### Added

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

- `SOLIDARITYNODE_ENVIRONMENT` replaced by `APP_ENV`; `.env.example` placeholders are plain `change-me`, with a comment per setting.
- Ports and URLs use `127.0.0.1`.
