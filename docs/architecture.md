# Architecture

> Status: v0.1 platform mechanics (no scientific method yet: the only model is the diagnostic model `diagnostic-v0`). It will grow with each module. The science is specified in [`docs/specs/`](specs/README.md); decisions are recorded in [`docs/adr/`](adr/README.md).

## 1. Components

```mermaid
flowchart LR
    subgraph Browser
        FE["frontend<br/>React + TypeScript (Vite)"]
    end
    subgraph Containers["compose.yaml (Podman default, Docker supported)"]
        NGX["frontend container<br/>nginx-unprivileged :8080"]
        BE["backend<br/>FastAPI :8000"]
        JOBS["worker service<br/>PostgreSQL job queue (ADR 0006)"]
        DB[("PostgreSQL + PostGIS<br/>data versions, scenarios, runs,<br/>result summaries")]
    end
    FILES[("results volume<br/>Parquet samples (ADR 0008)")]
    CORE["core<br/>solidaritynode_core<br/>(pure Python library)"]

    FE -->|"/api/*"| NGX -->|proxy| BE
    BE --> DB
    BE -->|"queue job"| DB
    DB -->|"claim job"| JOBS
    JOBS --> DB
    JOBS --> CORE
    BE --> CORE
    JOBS --> FILES
```

| Component | Path | Responsibility | Depends on |
| --- | --- | --- | --- |
| `core` | `core/` | Domain model and modelling methods (accessibility, need, vulnerability, dynamics, resilience). No web framework, no database driver. | NumPy, xarray |
| `backend` | `backend/` | HTTP API: data package import, users and roles, scenarios, runs, results, comparison, export; the worker process; persistence. | `core`, FastAPI, SQLAlchemy, Alembic, argon2-cffi, PyArrow |
| `worker` | `backend/` (same image) | Runs queued jobs (model runs) outside the request cycle. | `core`, PostgreSQL |
| `frontend` | `frontend/` | Web UI: study area, scenarios, runs, comparison, admin; maps with Leaflet (ADR 0007). | backend API over HTTP |
| database | `compose.yaml` | Data versions, scenarios, runs and result summaries in PostgreSQL/PostGIS. | — |
| files | `results` volume | Per-sample results in Parquet, package uploads. | — |

## 2. Dependency direction

```mermaid
flowchart LR
    frontend -. HTTP only .-> backend
    backend --> core
    core -. never .-x backend
    core -. never .-x frontend
```

- `backend → core`, never the reverse. `core` must not import `backend`, `frontend`, any web framework or any database layer.
- Enforced by `core/tests/test_package.py` (AST scan of imports and of declared dependencies) and by the ruff `banned-api` rule in `core/pyproject.toml`.
- The frontend talks to the backend only through the HTTP API (`frontend/src/api/client.ts`).

## 3. The paper pipeline

The four papers form a pipeline; each `core` module implements parts of one or more papers (module map: [`specs/00-domain-model.md` §6](specs/00-domain-model.md)).

```mermaid
flowchart TB
    subgraph P1["Paper 1: baseline"]
        ACC[accessibility] --> CAP["capacity<br/>2SFCA, OQ-2"]
        DEM[demand] --> SG[service_gap]
        CAP --> SG
    end
    subgraph P2["Paper 2: hidden need"]
        SS["Social Susceptibility<br/>SS_i,g,s"] --> NTU["non-take-up level<br/>(latent)"]
        NBG[need-based gap] --> NTU
        AD[access deterrence] --> NTU
        ALT[outside alternatives] --> NTU
        NTU --> ETN["Estimated Total Need<br/>Population × p × k"]
    end
    subgraph P3["Paper 3: disruption and vulnerability"]
        SCN["scenarios<br/>DS_f,c, rationing"] --> GE[Group Exposure]
        SCN --> SL["Service Loss<br/>ΔPUN / ETN"]
        GE --> V["vulnerability relationship<br/>P(V | GE, SL, SS)"]
        SL --> V
    end
    subgraph P4["Paper 4: operations, dynamics, resilience"]
        TIX[(anonymous tickets)] --> OPS["operations<br/>indicators, facility state"]
        OPS --> DYN["dynamics<br/>territorial state, DBN"]
        DYN --> OBS["observed GE(t), SL(t)"]
        OBS --> EXP[expected consequence]
        DYN --> TRJ[recovery trajectory]
        TRJ --> RES[resilience]
        EXP --> UPD["parameter learning<br/>of P(V | GE, SL, SS)"]
    end
    CAP -->|supply| NBG
    ACC --> AD
    SS --> V
    ETN --> SL
    CAP --> SL
    V --> EXP
    TIX -. "observed use, take-up learning (OQ-8)" .-> NTU
```

Cross-cutting modules used by all papers: `model`, `bayes`, `uncertainty` (Monte Carlo), `sensitivity`, `validation`.

Key separations (AGENTS.md invariants): vulnerability (a relationship, Paper 3) is not resilience (a trajectory property, Paper 4); a facility's state is not a unit's service loss; estimated demand is not need; a social group is not its susceptibility.

## 4. Ticket data flow

Anonymous request tickets (Paper 4 §4.1) are the only operational data the platform collects.

```mermaid
sequenceDiagram
    participant P as Person (QR / appointment form)
    participant API as backend /requests (not yet implemented)
    participant DB as PostGIS
    participant J as background job
    participant C as core.operations / dynamics / resilience
    P->>API: unit, group, service, facility (OQ-29), timestamps, first-request flag
    Note over API: schema rejects any other field (no names, contacts, addresses, device ids)
    API->>DB: store ticket (only after ADR 0010 / OQ-21 rules exist)
    J->>DB: read tickets + recording coverage per facility and period
    J->>C: operational indicators, facility state, observed GE(t), SL(t)
    C-->>J: trajectories, updated CPT parameters, resilience
    J->>DB: result index (arrays in Parquet)
```

- Privacy rules (minimum cell sizes, retention, aggregation) are **open (OQ-21)** and must be decided in ADR 0010 before any ticket is stored.
- Only facilities with full or known recording coverage feed learning (OQ-8).
- Tickets record the facility where the request is made or scheduled (OQ-29, decided), so indicators, functional state and recording coverage can be computed per facility. The facility field follows the OQ-21 rules.

## 5. Background jobs and runs

Model runs never execute inside a request handler.

```mermaid
sequenceDiagram
    participant UI as frontend
    participant API as backend
    participant DB as PostgreSQL
    participant W as worker
    participant C as core (model registry)
    UI->>API: POST /runs (scenario, version, seed, config)
    API->>DB: input hash; reuse a succeeded run, or insert run + queued job
    W->>DB: claim job (FOR UPDATE SKIP LOCKED)
    W->>C: diagnostic-v0(study area, scenario, config, seed, progress)
    C-->>W: progress callbacks (cancel checked here)
    W->>DB: run_results, run_tables; job succeeded
    W->>W: samples.parquet in the results volume
    UI->>API: GET /runs/{id} (poll status and progress)
```

- Interface: `JobRunner` (`submit(kind, payload)`, `info`, `cancel`) in `backend/.../jobs/`;
  implementation `PostgresJobRunner`; worker `python -m solidaritynode_backend.worker` (ADR 0006).
- A stopped worker marks its running job failed; a restarted worker fails jobs it left running.
- Runs record every reproducibility field and an input hash (ADR 0017); models come from the core
  registry (`solidaritynode_core.model.get_registry`), which holds only `diagnostic-v0`.

## 6. Containers and local development

- `make up` builds and starts `db`, `backend`, `worker` and `frontend` with `$(COMPOSE)` (default `podman compose`). Docker: `CONTAINER_ENGINE=docker COMPOSE="docker compose" make up`. ADR 0011.
- Ports (non-privileged, bound to 127.0.0.1): frontend 8080, backend 8000, database 5432; configurable in `.env`.
- The backend container runs `alembic upgrade head` before starting the API.
- Database data lives in the named volume `db-data`, run samples and package uploads in `results`; there are no bind mounts, so the stack behaves the same under WSL2.
- `make up` passes `GIT_COMMIT` to both image builds; `/version` and the frontend footer show it with `APP_ENV`, so a tester knows which build is running. Outside `development` and `test`, the backend refuses `change-me` secrets.
- `make uat` resets the database, starts the stack, imports demo package 1.0.0 (which queues the baseline run), seeds the development demo users and prints URLs and credentials; see [`docs/uat/`](uat/README.md).

## 7. Deployment and data packages

Spec 00 §3 describes one codebase running in two roles. v0.1 implements the municipal installation (`DEPLOYMENT_MODE=municipality`) with manual package import; hub onboarding comes next (ADR 0012). ADRs 0012, 0013 and 0015–0017 are accepted for v0.1; ADR 0014 (upward flow) stays open and nothing is sent upwards.

```mermaid
flowchart LR
    subgraph HUB["hub (ADR 0012)"]
        RAW[("national raw sources<br/>boundaries, network,<br/>population, DEM")]
        ONB["onboarding<br/>clip + buffer, clean, checks<br/>DP-NNN notes"]
        PKG[("data packages<br/>versioned, checksummed<br/>study area + buffer (ADR 0013, OQ-28)")]
        AGG[("aggregated indicators<br/>(optional)")]
        RAW --> ONB --> PKG
    end
    subgraph MUN["municipal installation (one per study area)"]
        IMP["package import<br/>preview of changes"]
        APP["scenarios (ADR 0016), runs (ADR 0017),<br/>results, users (ADR 0015)"]
        TIX[("anonymous tickets<br/>never leave the installation")]
        IMP --> APP
        TIX --> APP
    end
    PKG -->|"download / import"| IMP
    APP -.->|"opt-in, aggregated,<br/>anonymised only (ADR 0014, OQ-21)"| AGG
```

- The same images run as `municipality` or `hub`, chosen by `DEPLOYMENT_MODE` (ADR 0012).
- Data packages carry a `manifest.json` listing files with checksums, layer coverage, changelog and the `DP-NNN` processing notes behind the data (format in ADR 0013; demo packages in `data/synthetic/packages/`, DP-002). Import validates, previews changes and imports in one transaction; every version is kept and runs point to theirs.
- Core units next to a buffer municipality without facility data carry an edge-effect warning (OQ-28, warning only); results are reported for core units only.
- Runs record scenario version, package version, git commit, model and parameter version, seed and configuration (ADR 0017).

