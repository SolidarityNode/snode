# 0006. Background job queue

- Status: Proposed (stub, needs a human decision)
- Date: 2026-11-24
- Related: AGENTS.md "Long-running simulations run as background jobs"; `backend/src/solidaritynode_backend/jobs/`

## Context

Monte Carlo runs and scenario sweeps can take minutes to hours and must not run inside a request handler. The bootstrap provides a `JobRunner` protocol and an in-process thread-pool runner for development only (jobs are lost on restart, no result storage, no retries).

## Options to evaluate

1. **PostgreSQL-backed queue** (for example `procrastinate`, or `SELECT … FOR UPDATE SKIP LOCKED` by hand): no new infrastructure; check licences (procrastinate is MIT).
2. **RQ** (BSD) or **Dramatiq** (LGPL-3.0) with Redis/Valkey: simple workers; adds a service.
3. **Celery** (BSD): feature-rich, heavier.
4. **Arq** (MIT): asyncio, Redis.
5. Keep jobs as separate **containers/processes** started per run.

## Questions to answer before deciding

- Expected run duration, concurrency and need for cancellation/progress reporting?
- Should job state live in PostGIS with the run metadata?
- How do workers access Parquet outputs (shared volume, object storage)?
- Rootless Podman compatibility of the extra services.

## Decision

Not decided.

## Consequences

To be written with the decision.
