# Hub onboarding

The hub (`DEPLOYMENT_MODE=hub`, ADR 0012) keeps national raw sources, onboards municipalities
one by one, curates their facilities and publishes data packages (ADR 0013) that municipal
installations import. Code: `backend/src/solidaritynode_backend/services/hub/`, router
`routers/hub.py`; tables of migration 0011 (they exist only in a hub database). User guide:
[Hub](../user-guide/hub.md); processing notes DP-003 to DP-006.

## Onboarding states

Each municipality has one status. Transitions are stored with who and when
(`hub_onboarding_events`).

```mermaid
stateDiagram-v2
    [*] --> not_started: boundaries source registered
    not_started --> base_ready: base step succeeded (job)
    base_ready --> facilities_in_progress: first facility changeset approved
    base_ready --> in_review: administrator
    facilities_in_progress --> in_review: administrator ("ready for review")
    in_review --> facilities_in_progress: administrator ("send back")
    base_ready --> published: package of a study area with it as core
    facilities_in_progress --> published: package published
    in_review --> published: package published
    published --> published: later changes mark study areas "update available"
```

A municipality onboarded only as **buffer** of a neighbour has base data but stays
`not_started` until it is onboarded itself.

## Facility import and changesets

```mermaid
sequenceDiagram
    actor E as Analyst or administrator
    actor A as Administrator
    participant UI as Hub UI
    participant API as /hub API
    participant DB as hub database
    E->>UI: choose municipality, upload CSV / XLSX / GeoPackage
    UI->>API: POST /hub/facility-imports (file streamed, size and type limits)
    API->>API: parse; drop personal-data columns and values
    API->>DB: read municipality, units, nodes, existing facilities
    API->>API: validate rows, locate points, match by id then external id, find duplicates
    API->>DB: store pending changeset (report, items with field-level diff)
    API-->>UI: validation report and preview (added, updated, closed)
    A->>UI: approve (complete list: type the number of closures) or reject
    UI->>API: POST /hub/changesets/{id}/approve
    API->>DB: check facilities did not change since the preview
    API->>DB: new ids HF-nnnnnn, update, close with valid_to (never delete)
    API->>DB: processing record (DP-004), status facilities_in_progress
    API-->>UI: approved changeset (history of every facility)
```

A manual edit (`POST /hub/facilities/edits`) is turned into template rows and follows the same
path, as changeset kind `manual`.

## Publishing and propagation

```mermaid
sequenceDiagram
    actor A as Administrator (hub)
    participant API as /hub API
    participant W as worker
    participant DB as hub database
    participant FS as hub storage volume
    actor M as Administrator (municipality)
    participant I as municipal installation
    A->>API: POST /hub/study-areas/{id}/publish
    API->>DB: next version (1.0.0, then minor or patch), row "building", job
    API-->>A: 202 version and job id
    W->>DB: select core and buffer features valid today plus all of the previous version
    W->>FS: layers.gpkg, tables, manifest (coverage, provenance, changelog, checksums)
    W->>W: validate with the installation's package reader
    W->>FS: directory and .zip
    W->>DB: package "published" (immutable), feature fingerprints, status published
    Note over DB: later: a neighbour is onboarded or a facility changes
    API->>DB: GET /hub/study-areas compares the next package with the last one
    API-->>A: study area listed as "update available" with a draft changelog
    A->>API: publish again (deliberate action)
    M->>I: make import-package PKG=... or Admin screen: upload, preview, confirm
    I->>I: validate, preview changes, import, baseline run, revalidate scenarios
```

The installation always opens the connection (ADR 0012): packages are downloaded from the hub
and imported by hand; nothing is pushed to an installation.

## From raw source to package

```mermaid
flowchart LR
    subgraph REG["Sources (registered, not processed)"]
        B[(boundaries.gpkg)]
        U[(spatial_units.gpkg)]
        N[(network.gpkg)]
        P[(population.csv)]
        C[(groups.csv, services.csv)]
    end
    subgraph BASE["Base step per municipality (job, DP-003)"]
        S["stream with bbox prefilter"] --> SEL["select municipality + buffer<br/>(rule configurable, OQ-28)"]
        SEL --> IDS["stable ids: official codes,<br/>reuse existing, close missing"]
        IDS --> CHK["checks: CRS, validity,<br/>connectivity, population"]
    end
    subgraph FAC["Facilities (DP-004)"]
        F[/CSV, XLSX, GeoPackage/] --> V["validation report"] --> CS["changeset preview"] --> AP["approval"]
    end
    CUR[("hub_features<br/>curated, never deleted")]
    REC[("processing records<br/>inputs, SHA-256, checks")]
    PUB["package assembly (job, DP-006)"]
    PKG[("package x.y.z<br/>layers.gpkg, tables, manifest")]
    B & U & N & P --> S
    CHK --> CUR
    AP --> CUR
    CHK --> REC
    AP --> REC
    CUR --> PUB
    C --> PUB
    REC -->|provenance, changelog| PUB
    PUB --> PKG
    PKG -->|"download, make import-package"| INST["municipal installation"]
```

## Notes

- Long work (base step, package assembly) runs in the worker (ADR 0006) with progress and
  cancellation; a cancelled or failed job stores nothing (one transaction).
- Sources are copied and hashed in 1 MiB chunks; GeoPackages are read row by row with a
  bounding-box prefilter; CSV sources are streamed. Nothing loads a national file whole.
- Geoprocessing uses PostGIS in the hub database (no new Python dependency); QGIS stays a
  manual alternative in `data-processing/qgis/`.
- Roles: viewers read; analysts upload facility files and propose edits; administrators
  register sources, run the base step, approve changesets, create study areas and publish.
