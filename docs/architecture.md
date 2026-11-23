# Architecture

> Status: v0 skeleton. Describes the structure set up by the bootstrap; it will grow with each module. The science is specified in [`docs/specs/`](specs/README.md); decisions are recorded in [`docs/adr/`](adr/README.md).

## 1. Components

```mermaid
flowchart LR
    subgraph Browser
        FE["frontend<br/>React + TypeScript (Vite)"]
    end
    subgraph Containers["compose.yaml (Podman default, Docker supported)"]
        NGX["frontend container<br/>nginx-unprivileged :8080"]
        BE["backend<br/>FastAPI :8000"]
        JOBS["background jobs<br/>(JobRunner, ADR 0006)"]
        DB[("PostgreSQL + PostGIS<br/>metadata, result index")]
    end
    FILES[("Parquet files<br/>large arrays (ADR 0008)")]
    CORE["core<br/>solidaritynode_core<br/>(pure Python library)"]

    FE -->|"/api/*"| NGX -->|proxy| BE
    BE --> DB
    BE --> JOBS
    JOBS --> CORE
    BE --> CORE
    JOBS --> FILES
```

| Component | Path | Responsibility | Depends on |
| --- | --- | --- | --- |
| `core` | `core/` | Domain model and modelling methods (accessibility, need, vulnerability, dynamics, resilience). No web framework, no database driver. | NumPy, xarray |
| `backend` | `backend/` | HTTP API, scenario and run management, anonymous request logging, background jobs, persistence. | `core`, FastAPI, SQLAlchemy, Alembic |
| `frontend` | `frontend/` | Web UI: scenarios, results, maps (map library: ADR 0007). | backend API over HTTP |
| database | `compose.yaml` | Metadata and result indexes in PostgreSQL/PostGIS. | — |
| files | `data/` (not in git) | Large datasets and result arrays in Parquet. | — |

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

Key separations (CLAUDE.md invariants): vulnerability (a relationship, Paper 3) is not resilience (a trajectory property, Paper 4); a facility's state is not a unit's service loss; estimated demand is not need; a social group is not its susceptibility.

## 4. Ticket data flow

Anonymous request tickets (Paper 4 §4.1) are the only operational data the platform collects.

```mermaid
sequenceDiagram
    participant P as Person (QR / appointment form)
    participant API as backend /requests (not yet implemented)
    participant DB as PostGIS
    participant J as background job
    participant C as core.operations / dynamics / resilience
    P->>API: unit, group, service, timestamps, first-request flag
    Note over API: schema rejects any other field (no names, contacts, addresses, device ids)
    API->>DB: store ticket (only after ADR 0010 / OQ-21 rules exist)
    J->>DB: read tickets + recording coverage per facility and period
    J->>C: operational indicators, facility state, observed GE(t), SL(t)
    C-->>J: trajectories, updated CPT parameters, resilience
    J->>DB: result index (arrays in Parquet)
```

- Privacy rules (minimum cell sizes, retention, aggregation) are **open (OQ-21)** and must be decided in ADR 0010 before any ticket is stored.
- Only facilities with full or known recording coverage feed learning (OQ-8).
- Spec gap to raise: tickets carry no facility, but indicators, functional state and recording coverage are per facility (see `core/src/solidaritynode_core/operations/__init__.py`).

## 5. Background jobs

Long-running simulations (Monte Carlo, scenario sweeps, DBN runs) never run inside a request handler.

- `backend/src/solidaritynode_backend/jobs/` defines a `JobRunner` protocol (`submit`, `info`, `shutdown`) and an `InProcessJobRunner` (thread pool) for development and tests.
- The production queue is open (ADR 0006). Routers depend only on `JobRunner`, so the queue can change without touching them.
- Jobs call `core` directly and write large outputs to Parquet; the database stores the index (ADR 0008).

## 6. Containers and local development

- `make up` builds and starts `db`, `backend` and `frontend` with `$(COMPOSE)` (default `podman compose`). Docker: `CONTAINER_ENGINE=docker COMPOSE="docker compose" make up`. ADR 0011.
- Ports (non-privileged, bound to 127.0.0.1): frontend 8080, backend 8000, database 5432; configurable in `.env`.
- The backend container runs `alembic upgrade head` before starting the API.
- Database data lives in the named volume `db-data`; there are no bind mounts, so the stack behaves the same under WSL2.
