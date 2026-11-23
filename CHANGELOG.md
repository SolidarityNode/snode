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
