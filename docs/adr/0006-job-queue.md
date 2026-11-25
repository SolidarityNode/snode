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
  failed | cancelled`, progress 0–100, error, `cancel_requested`, worker name, timestamps,
  `heartbeat_at`).
- **Claiming commits before execution.** The worker claims the oldest queued job with
  `SELECT … FOR UPDATE SKIP LOCKED` and sets it `running` in one short transaction, which
  commits before the handler starts. No transaction or row lock is held while a job runs, so the
  API can read and flag the job and a sweep can fail it
  (`backend/tests/test_worker.py::test_claim_commits_before_the_job_runs`).
- The bootstrap `JobRunner` interface is kept but evolved: a job is a `kind` plus a JSON payload
  (not a Python callable, so it can cross processes), and the interface gains `cancel`. The
  in-process thread-pool runner is removed. `PostgresJobRunner` implements it; routers depend
  only on the interface.
- The worker (`python -m solidaritynode_backend.worker`) is its own compose service with the
  backend image. It runs one job at a time, reports progress to the job row, stops a job at its
  next progress step when cancellation is requested, and marks the running job failed with a
  clear message on `SIGTERM`/`SIGINT`.
- **Lease and heartbeat.** While a job runs, a separate thread of its worker sets
  `jobs.heartbeat_at = now()` every `SOLIDARITYNODE_JOB_HEARTBEAT_SECONDS` (default 10). Any
  worker, at start and then every heartbeat interval while idle, marks running jobs whose
  heartbeat is older than `SOLIDARITYNODE_JOB_STALE_SECONDS` (default 120, at least twice the
  heartbeat) as failed ("Interrupted: the worker (…) stopped while this run was running (no
  heartbeat since …). No results were stored. Start the run again."). A worker never overwrites
  a job that is no longer `running`, so a swept job stays failed. The worker name
  (`SOLIDARITYNODE_WORKER_NAME`) is recorded for logs only; recovery no longer depends on it.
- **Maximum runtime per job kind** (optional, `SOLIDARITYNODE_JOB_MAX_RUNTIME_SECONDS`, for
  example `run=3600`; default empty, so the diagnostic model's `run` jobs have no limit). A job
  over its limit is stopped at its next progress step, like a cancel, and marked **failed**
  ("Stopped: the job ran longer than the maximum runtime of … s set for '…' jobs …").
- Outputs are shared through the `results` volume mounted in both containers (ADR 0008).

Maintainer decision (2026-11-25, PR #6): the evolved interface (`submit(kind, payload)` plus
`cancel`) and the removal of the in-process runner are accepted.

**Why:** no new service or dependency, job state lives next to the run metadata in one
transaction, rootless Podman needs nothing extra, and runs are short at this stage. Cancellation
and progress are simple column updates.

## Consequences

- Polling (1 s) adds a little latency; `LISTEN/NOTIFY` can replace it later.
- One worker process, one job at a time. Several workers are possible (`SKIP LOCKED`, and the
  lease does not depend on names).
- A killed worker's job is failed only after `SOLIDARITYNODE_JOB_STALE_SECONDS` (default 2
  minutes), not at the instant of restart; a busy worker sweeps only after its current job.
- Cancellation and the maximum runtime are **cooperative**: they act at the handler's next
  progress step. A handler that never reports progress cannot be stopped this way (the
  diagnostic model reports at every step).
- No retries or scheduling.

### When to revisit

Replace the hand-written queue when any of these happens:

1. a run takes longer than **10 minutes**;
2. **more than one user** regularly waits for runs at the same time;
3. **scheduled jobs** are needed (for example periodic imports or reports);
4. **retries for external calls** are needed (for example downloads from the hub or open data
   services).

First candidate: **procrastinate** (MIT, PostgreSQL only: no new service, keeps job state next to
the run metadata). RQ, Dramatiq or Celery remain options if a broker becomes acceptable. The
`JobRunner` interface keeps the change local to `jobs/` and the worker. The **hub-onboarding
PR** (ADR 0012, 0014) is likely to hit triggers 3 and 4 (scheduled package builds and calls to
external sources), so revisit this ADR there.
