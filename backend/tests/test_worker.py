"""Worker lease (heartbeat), stale-job sweep, maximum runtime and claim transaction (ADR 0006)."""

from __future__ import annotations

import time
import uuid
from collections.abc import Mapping
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from solidaritynode_backend.config import Settings
from solidaritynode_backend.jobs import JobContext, PostgresJobRunner
from solidaritynode_backend.worker import Handler, Worker


def _submit(engine: Engine, kind: str = "test") -> uuid.UUID:
    with Session(engine) as db, db.begin():
        return uuid.UUID(PostgresJobRunner(db).submit(kind, {}))


def _job(engine: Engine, job_id: uuid.UUID) -> Any:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT status, error, worker, heartbeat_at, started_at FROM jobs WHERE id = :id"),
            {"id": job_id},
        ).one()


def _worker(engine: Engine, name: str, handlers: Mapping[str, Handler], **kw: Any) -> Worker:
    return Worker(engine, name, handlers, **kw)


def _noop(ctx: JobContext, payload: Mapping[str, Any]) -> None:
    ctx.progress(1.0)


def test_stale_heartbeat_is_failed_by_a_different_worker(engine: Engine) -> None:
    dead = _worker(engine, "worker-a", {"test": _noop})
    other = _worker(engine, "worker-b", {"test": _noop}, stale_s=120)
    stale, fresh = _submit(engine), _submit(engine)
    assert dead.claim() is not None
    assert dead.claim() is not None
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE jobs SET heartbeat_at = now() - interval '5 minutes' WHERE id = :id"),
            {"id": stale},
        )
    assert other.fail_stale() == 1
    row = _job(engine, stale)
    assert row.status == "failed"
    assert row.error.startswith("Interrupted: the worker (worker-a) stopped")
    assert "no heartbeat since" in row.error
    assert row.error.endswith("Start the run again.")
    assert _job(engine, fresh).status == "running"  # lease still valid: left alone
    assert other.fail_stale() == 0


def test_heartbeat_is_renewed_from_a_separate_thread_while_a_job_runs(engine: Engine) -> None:
    seen: list[Any] = []

    def slow(ctx: JobContext, payload: Mapping[str, Any]) -> None:
        time.sleep(0.4)  # no progress call: only the heartbeat thread touches the row
        seen.append(_job(engine, uuid.UUID(ctx.job_id)))

    job_id = _submit(engine)
    assert _worker(engine, "w", {"test": slow}, heartbeat_s=0.05, stale_s=1).run_once()
    assert seen[0].status == "running"
    assert seen[0].heartbeat_at > seen[0].started_at
    assert _job(engine, job_id).status == "succeeded"


def test_a_job_failed_as_stale_is_not_resurrected_by_its_worker(engine: Engine) -> None:
    def swept(ctx: JobContext, payload: Mapping[str, Any]) -> None:
        with engine.begin() as conn:  # another worker fails the job meanwhile
            conn.execute(text("UPDATE jobs SET status = 'failed', error = 'Interrupted: x'"))

    job_id = _submit(engine)
    _worker(engine, "w", {"test": swept}).run_once()
    assert _job(engine, job_id).status == "failed"


def test_max_runtime_cancels_and_fails_the_job(engine: Engine) -> None:
    progressed: list[float] = []

    def long(ctx: JobContext, payload: Mapping[str, Any]) -> None:
        for step in range(1, 50):
            time.sleep(0.02)
            ctx.progress(step / 50)
            progressed.append(step / 50)

    job_id = _submit(engine, "long")
    worker = _worker(engine, "w", {"long": long}, max_runtime_s={"long": 0.1})
    assert worker.run_once()
    row = _job(engine, job_id)
    assert row.status == "failed"
    assert row.error.startswith("Stopped: the job ran longer than the maximum runtime of 0.1 s")
    assert "'long' jobs" in row.error
    assert "SOLIDARITYNODE_JOB_MAX_RUNTIME_SECONDS" in row.error
    assert 0 < len(progressed) < 49  # stopped at a progress step, well before the end
    other = _submit(engine, "other")  # kinds without a limit are not affected
    unlimited = _worker(engine, "w", {"other": long}, max_runtime_s={"long": 0.1})
    assert unlimited.run_once()
    assert _job(engine, other).status == "succeeded"


def test_claim_commits_before_the_job_runs(engine: Engine) -> None:
    checks: dict[str, Any] = {}

    def probe(ctx: JobContext, payload: Mapping[str, Any]) -> None:
        with engine.begin() as conn:
            # Another session sees the claim (committed) and can lock the row at once: the worker
            # holds no row lock. NOWAIT raises instead of waiting if a lock were held.
            checks["status"] = conn.execute(
                text("SELECT status FROM jobs WHERE id = :id FOR UPDATE NOWAIT"),
                {"id": uuid.UUID(ctx.job_id)},
            ).scalar_one()
            checks["idle_in_transaction"] = conn.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                    "AND pid <> pg_backend_pid() AND state LIKE 'idle in transaction%'"
                )
            ).scalar_one()

    _submit(engine)
    assert _worker(engine, "w", {"test": probe}).run_once()
    assert checks == {"status": "running", "idle_in_transaction": 0}


def test_job_timing_settings() -> None:
    assert Settings().max_runtimes() == {}  # default: no limit, also for the diagnostic model
    limits = Settings(job_max_runtime_seconds="run=3600, other=1.5").max_runtimes()
    assert limits == {"run": 3600.0, "other": 1.5}
    with pytest.raises(ValueError, match="kind=seconds"):
        Settings(job_max_runtime_seconds="run")
    with pytest.raises(ValueError, match="twice"):
        Settings(job_heartbeat_seconds=100, job_stale_seconds=120)
