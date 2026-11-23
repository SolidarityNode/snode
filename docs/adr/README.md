# Architecture decision records

Short records of significant decisions (CLAUDE.md). One file per decision, numbered, never renumbered. Status: `Proposed`, `Accepted`, `Superseded by NNNN`, `Rejected`. Copy [`template.md`](template.md) for a new record.

Methodological decisions (formulas, model structure) are recorded in [`docs/specs/open-questions.md`](../specs/open-questions.md); ADRs record technical and project decisions. An ADR may implement or depend on an `OQ-n`.

| ADR | Title | Status | Related |
| --- | --- | --- | --- |
| [0001](0001-monorepo.md) | Monorepo with core, backend, frontend | Accepted | |
| [0002](0002-license-agpl.md) | AGPL-3.0 licence | Accepted | |
| [0003](0003-core-data-model.md) | Core data model and the indexed-values container | Accepted | OQ-1, OQ-6, OQ-24, OQ-25 |
| [0004](0004-bn-dbn-library.md) | BN/DBN library | Proposed (stub) | OQ-7, OQ-17 |
| [0005](0005-inference-and-discretisation.md) | Inference approach, CPT size and discretisation | Proposed (stub) | OQ-7, OQ-11, OQ-15 |
| [0006](0006-job-queue.md) | Background job queue | Proposed (stub) | |
| [0007](0007-map-library.md) | Frontend map library | Proposed (stub) | |
| [0008](0008-large-array-storage.md) | Storage of large arrays (Parquet) | Proposed (stub) | |
| [0009](0009-geospatial-data-sources.md) | Geospatial data sources | Proposed (stub) | OQ-22 |
| [0010](0010-ticket-privacy.md) | Privacy rules for request tickets | Proposed (stub) | OQ-21, OQ-6, OQ-8 |
| [0011](0011-container-engine.md) | Container engine (Podman default, Docker supported) | Proposed (stub) | |
