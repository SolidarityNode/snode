# Architecture decision records

Short records of significant decisions (AGENTS.md). One file per decision, numbered, never renumbered. Status: `Proposed`, `Accepted`, `Superseded by NNNN`, `Rejected`. Copy [`template.md`](template.md) for a new record.

Methodological decisions (formulas, model structure) are recorded in [`docs/specs/open-questions.md`](../specs/open-questions.md); ADRs record technical and project decisions. An ADR may implement or depend on an `OQ-n`.

The table below is generated from the header lines (`Status`, `Date`, `Related`) of each ADR by `make docs-generate`; CI fails if it is out of date. Edit the ADR, not the table.

<!-- BEGIN GENERATED: adr-index (scripts/docs_indexes.py; edit the ADR files, then run make docs-generate) -->
| ADR | Title | Status | Date | Related open questions |
| --- | --- | --- | --- | --- |
| [0001](0001-monorepo.md) | Monorepo with core, backend, frontend | Accepted | 2026-11-24 |  |
| [0002](0002-license-agpl.md) | AGPL-3.0 licence | Accepted | 2026-11-24 |  |
| [0003](0003-core-data-model.md) | Core data model and the indexed-values container | Accepted | 2026-11-24 | OQ-1, OQ-6, OQ-24, OQ-25 |
| [0004](0004-bn-dbn-library.md) | BN/DBN library | Proposed (stub, needs a human decision) | 2026-11-24 | OQ-7, OQ-17, OQ-27 |
| [0005](0005-inference-and-discretisation.md) | Inference approach, CPT size and discretisation | Proposed (stub, needs a human decision) | 2026-11-24 | OQ-4, OQ-7, OQ-11, OQ-15 |
| [0006](0006-job-queue.md) | Background job queue | Accepted for v0.1, to be revisited | 2026-11-24 |  |
| [0007](0007-map-library.md) | Frontend map library | Accepted for v0.1, to be revisited | 2026-11-24 |  |
| [0008](0008-large-array-storage.md) | Storage of large arrays (Parquet) | Accepted for v0.1, to be revisited | 2026-11-24 |  |
| [0009](0009-geospatial-data-sources.md) | Geospatial data sources | Proposed (stub, needs a human decision) | 2026-11-24 | OQ-22 |
| [0010](0010-ticket-privacy.md) | Privacy rules for request tickets | Proposed (stub, needs a human decision) | 2026-11-24 | OQ-6, OQ-8, OQ-21, OQ-29 |
| [0011](0011-container-engine.md) | Container engine (Podman default, Docker supported) | Proposed (stub, needs a human decision) | 2026-11-24 |  |
| [0012](0012-deployment-model.md) | Deployment model: municipal installations and a hub | Accepted for v0.1, to be revisited | 2026-11-24 | OQ-21, OQ-28 |
| [0013](0013-data-packages.md) | Data packages: format, versioning, checksums and buffer | Accepted for v0.1, to be revisited | 2026-11-24 | OQ-28 |
| [0014](0014-upward-data-flow.md) | Upward data flow from municipalities to the hub | Proposed (Part A, facility corrections: proposal for v0.2, under review in PR #14; Part B, aggregated indicators: stub, needs a human decision) | 2026-11-24 | OQ-8, OQ-16, OQ-21, OQ-27 |
| [0015](0015-authentication-and-roles.md) | Authentication and roles | Accepted for v0.1, to be revisited | 2026-11-24 | OQ-21 |
| [0016](0016-scenario-schema-and-versioning.md) | Scenario schema and versioning | Accepted for v0.1, to be revisited | 2026-11-24 | OQ-16, OQ-24 |
| [0017](0017-run-reproducibility-and-result-storage.md) | Run reproducibility and result storage | Accepted for v0.1, to be revisited | 2026-11-24 |  |
| [0018](0018-documentation-site.md) | Documentation site: MkDocs Material, mike, Mermaid | Accepted for v0.1, to be revisited | 2026-11-25 |  |
| [0019](0019-bilingual-documentation-site.md) | Bilingual documentation site: Greek user-facing pages with mkdocs-static-i18n | Accepted | 2026-11-26 |  |
| [0020](0020-paper-4-forecasting-and-digital-twin-boundary.md) | Boundary between Paper 4 forecasting and a future digital twin | Proposed (stub, needs a human decision) | 2026-11-26 | OQ-23, OQ-31, OQ-32, OQ-33, OQ-34, OQ-40 |
<!-- END GENERATED: adr-index -->
