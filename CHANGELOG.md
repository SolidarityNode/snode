# Changelog

All notable changes are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/) (while 0.x, see [docs/releasing.md](docs/releasing.md)).

Every pull request that changes behaviour adds a line under **Unreleased** (AGENTS.md). Each release section also states known limitations and upgrade notes for installations.

## [Unreleased]

### Added: for users

- **Documentation in Greek**: the home page, the whole user guide (including roles, data updates and the FAQ), concepts and the roadmap are on the documentation site in Greek, under `el/`, with a language switcher in the header that keeps the page and the version. Terms follow `docs/i18n/glossary.md` and button names are those of the Greek UI, with the English label the first time. Technical pages (architecture, ADRs, specs, open questions, paper revisions, data-processing notes, contributing, changelog) stay in English and are marked "(στα αγγλικά)" (ADR 0019).

- **Method notes of the maintainer (2026-11-26)** recorded in the specs: Paper 4 includes **forecasting** (two users, current picture, nowcast and forecast, risk maps from hazard forecasts, scheduled reproducible runs, decision support only, weekly and hourly time scales, one-month and conditional forecasts): OQ-31 to OQ-34, decided; new open questions on spatial dependence and neighbourhoods (OQ-35), group-specific travel time (OQ-36), the spatial unit for large municipalities (OQ-37) and Paper 4 forecasting details (OQ-38 to OQ-41); OQ-30 notes the pending confirmation; `paper-revisions.md` has the Paper 4 entries; ADR 0020 (proposed) on the boundary between Paper 4 forecasting and a future digital twin; the roadmap says Paper 4 includes forecasting.

### Fixed

- Greek UI: *owner* is «κάτοχος» everywhere (four texts said «ιδιοκτήτης»), as in the glossary.

### Added: technical

- Documentation tooling: `mkdocs-static-i18n` 1.3.1 (MIT) in `tools/docs/`. `scripts/docs_i18n.py`, run by `make lint` and the docs workflow, warns about Greek pages whose English source changed (front matter `translated_from_sha256`) and fails if a user-guide page has no Greek version; `make docs-stamp PAGE=…` records an updated translation. New glossary terms are marked *proposed*.

## [0.1.0] - unreleased

<!-- The maintainer replaces "unreleased" with the date of the v0.1.0 tag (docs/releasing.md). -->

First version: the **platform foundation** of a municipal installation, on synthetic data, with the diagnostic model only. Pull requests [#1](https://github.com/SolidarityNode/snode/pull/1) (bootstrap), [#3](https://github.com/SolidarityNode/snode/pull/3) (AGENTS.md), [#4](https://github.com/SolidarityNode/snode/pull/4) (CI), [#5](https://github.com/SolidarityNode/snode/pull/5) (OQ-29), [#6](https://github.com/SolidarityNode/snode/pull/6) (platform mechanics) and the documentation site.

### Added: for users

- **Sign-in and roles**: local accounts (administrator, analyst, viewer); passwords of at least 12 characters, common passwords refused; sign-in throttling with delays and temporary locks; the last active administrator is always kept (ADR 0015).
- **Study area** on a map (Leaflet): core and buffer units, facilities and network; data quality on every feature (verified by the municipality, open data, estimated); coverage per municipality and layer; **edge-effect warnings** for units next to a neighbour without facility data (OQ-28, warning only); keyboard navigation and a text list of every feature.
- **Scenarios**: versioned "what if" overlays built on the map (close an edge per mode, facility disruption severity, capacity changes in percent or absolute amounts), validated against the active data, private or shared; network and population changes accepted as recorded-only placeholders (ADR 0016).
- **Runs** in the background with progress and cancel; every run immutable and reproducible (scenario version, data version, code version, model and version, seed, configuration, environment); identical inputs reuse the earlier run (ADR 0017).
- **Results** by spatial unit, group and service with the median and a 90 % interval everywhere, an optional uncertainty map and data-quality layer; **comparison** with the baseline or across data versions of one scenario (one shared colour scale, difference of medians); **export** to CSV and GeoPackage with the reproducibility metadata.
- **Data packages** (ADR 0013): preview of changes, checksums, import in one transaction, every version kept, rollback to an earlier version (Admin screen, `make import-package`, `make activate-version`); after an update, a baseline run is queued and every scenario revalidated; old runs offer **Rerun on data X**.
- English and Greek interface, with the terms of `docs/i18n/glossary.md`; the footer names the build (backend version and commit, frontend commit, data version).
- `docs/concepts.md` for municipal staff; UAT checklists `docs/uat/00-bootstrap.md` and `docs/uat/01-platform.md` with screenshots.

### Added: technical

- Monorepo: `core` (Python 3.12, typed domain model and module interfaces, no web or database dependencies), `backend` (FastAPI, SQLAlchemy, Alembic, PostGIS), `frontend` (React, TypeScript, Vite), `docs`, synthetic data, Makefile; Podman by default, Docker supported (ADR 0001, 0011).
- `core`: domain model indexed by `spatial unit × social group × service × time` (ADR 0003), uncertain values, variable catalogue, model registry, scenario overlay with the order of application (OQ-30, proposed), summary statistics of samples, and the diagnostic model `diagnostic-v0` 0.2.1 (labelled "Diagnostic model: not a research result").
- `backend`: PostgreSQL job queue and `worker` service with heartbeat lease, cancel and optional maximum runtime (ADR 0006); results summaries in PostGIS and Monte Carlo samples in Parquet with SHA-256 (ADR 0008); deployment role `municipality` | `hub` locked in the database (ADR 0012); anonymous ticket schema with the facility field (OQ-29), nothing stored (ADR 0010); scenario JSON Schema and OpenAPI exported to `docs/schemas/` (`make schemas`); server messages with stable codes translated by the UI.
- Operations: `make setup`, `up`, `uat`, `reset`, `seed`, `check-config` (refuses placeholder secrets in production), `create-admin`, `db-shell`, `clear-login-locks`; `APP_ENV`; `/health`, `/health/ready`, `/version`.
- Synthetic demo dataset (DP-001) and demo packages 1.0.0 and 1.1.0 (DP-002), generated by scripts.
- Quality: ruff, mypy strict, ESLint, Prettier, Vitest, pytest, Playwright end-to-end test in a throw-away stack; CI per component, image builds with Podman and Docker, licence check, DCO check, Dependabot.
- Governance: AGPL-3.0-or-later, `AGENTS.md` rules for every contributor and coding agent, contributing guide, code of conduct, security and trademark policies, ADRs 0001–0017, open questions OQ-1 to OQ-30.

### Documentation

- Documentation site (MkDocs with the Material theme, versioned with mike, published to GitHub Pages): user guide with one page per screen, roles and FAQ; architecture pages per component with Mermaid diagrams of the run lifecycle, run statuses, data update flow, data model and scenario application order; roadmap; release process (`make docs`, `make docs-build`). The README and the docs home show the SN Kintsugi logo with the platform version from `VERSION`; the logo is also the site icon and favicon, and the logo with "SN Kintsugi" replaces the name in the header of the web application, which uses it as favicon too.
- Generated and CI-checked: the ADR index, the specifications index, the open-question counts (`make docs-generate`) and the dependency and licence report `docs/architecture/dependencies.md` (`make deps-report`); link checking of the README and docs.
- The platform version has one source, the file `VERSION` (`make version`, `make version-sync`, checked by `make lint`), and the run reproducibility record names it (`environment.solidaritynode`, not in the input hash).
- README as a short landing page; `CITATION.cff`; milestones per roadmap step and labels `paper:1` … `paper:4`.
- Rules: diagrams are Mermaid and change with the behaviour they describe; every PR that changes behaviour adds a line under **Unreleased** and updates the user guide page it affects.

### Known limitations

- **Diagnostic model only.** No research method is implemented; results check the platform and are not accessibility, need, vulnerability or resilience.
- **No hub onboarding yet.** Only the municipal installation is complete; data packages are imported by hand (roadmap step 2).
- **OpenStreetMap tiles are for development only.** Light interactive use within the OSMF tile usage policy; use `SOLIDARITYNODE_BASEMAP=blank` offline or for any heavier use, until a tile source for production is chosen.
- **No backup guide yet.** The database and the results volume must be backed up together; nothing is deleted automatically.
- Disruption severities, network and population changes are recorded only, with no effect on results.
- No request tickets are stored until the privacy rules are decided (OQ-21, ADR 0010).
- Synthetic data only.

### Upgrade notes

- First release: install from scratch (`make setup`, then `make up` and `make create-admin`, or `make uat` for a test machine). Runs queued before an upgrade fail with "Start the run again".

[Unreleased]: https://github.com/SolidarityNode/snode/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/SolidarityNode/snode/commits/v0.1.0
