# 0006. Background job queue

- Status: Accepted for v0.1, to be revisited
- Date: 2026-11-24 (accepted for v0.1: 2026-11-25)
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

**Accepted for v0.1, to be revisited: option 1, a PostgreSQL-backed queue written by hand**
(`SELECT … FOR UPDATE SKIP LOCKED`), consumed by a separate worker process.

- Jobs are rows in table `jobs` (kind, JSON payload, status `queued → running → succeeded |
  failed | cancelled`, progress 0–100, error, `cancel_requested`, worker name, timestamps).
- The bootstrap `JobRunner` interface is kept but evolved: a job is a `kind` plus a JSON payload
  (not a Python callable, so it can cross processes), and the interface gains `cancel`. The
  in-process thread-pool runner is removed. `PostgresJobRunner` implements it; routers depend
  only on the interface.
- The worker (`python -m solidaritynode_backend.worker`) is its own compose service with the
  backend image. It runs one job at a time, reports progress to the job row, stops a job at its
  next progress step when cancellation is requested, marks the running job failed with a clear
  message on `SIGTERM`/`SIGINT`, and on start marks jobs it was running when it died as failed
  ("Interrupted: … Start the run again.").
- Outputs are shared through the `results` volume mounted in both containers (ADR 0008).

Maintainer decision (2026-11-25, PR #6): the evolved interface (`submit(kind, payload)` plus
`cancel`) and the removal of the in-process runner are accepted.

**Why:** no new service or dependency, job state lives next to the run metadata in one
transaction, rootless Podman needs nothing extra, and runs are short at this stage. Cancellation
and progress are simple column updates.

## Consequences

- Polling (1 s) adds a little latency; `LISTEN/NOTIFY` can replace it later.
- One worker process, one job at a time. Several workers are possible (`SKIP LOCKED`) but each
  needs its own `SOLIDARITYNODE_WORKER_NAME` so restart recovery only fails its own jobs.
- No retries or scheduling. Revisit when Monte Carlo runs get long or concurrent (procrastinate,
  RQ or Celery remain options); the interface keeps that change local.
