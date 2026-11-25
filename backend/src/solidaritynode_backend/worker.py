"""Background worker: claims jobs from the PostgreSQL queue and runs them (ADR 0006).

Runs as its own compose service (``python -m solidaritynode_backend.worker``). One job at a time:

* claims the oldest queued job with ``SELECT … FOR UPDATE SKIP LOCKED`` in a short transaction
  that commits **before** the job runs, so no transaction or row lock is held while it runs;
* while the job runs, a separate thread renews the job's lease (``jobs.heartbeat_at``) every
  ``job_heartbeat_seconds``;
* reports progress to the job row; a cancel request, or a job over the maximum runtime of its
  kind (``job_max_runtime_seconds``), stops the job at its next progress step;
* on ``SIGTERM``/``SIGINT`` (for example ``make stop SERVICE=worker``) it marks the running job
  failed with a clear message and exits;
* at start and periodically it marks **any** running job whose heartbeat is older than
  ``job_stale_seconds`` as failed (its worker died, for example after ``SIGKILL``). The worker
  name is only recorded for logs.
"""

from __future__ import annotations

import contextlib
import logging
import signal
import sys
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from datetime import UTC, datetime
from functools import partial
from threading import Event, Thread
from types import FrameType
from typing import Any

from sqlalchemy import Engine, create_engine, text

from solidaritynode_backend.config import Settings, get_settings
from solidaritynode_backend.jobs import JobCancelledError, JobContext, JobStatus, JobTimedOutError
from solidaritynode_backend.services.installation import RoleMismatchError, check_role
from solidaritynode_backend.services.runs import RUN_JOB_KIND, execute_run

__all__ = ["Handler", "Worker", "WorkerStoppedError", "main"]

log = logging.getLogger("solidaritynode.worker")

type Handler = Callable[[JobContext, Mapping[str, Any]], None]

INTERRUPTED = (
    "Interrupted: the worker ({worker}) stopped while this run was running ({when}). "
    "No results were stored. Start the run again."
)
TIMED_OUT = (
    "Stopped: the job ran longer than the maximum runtime of {limit:g} s set for '{kind}' jobs "
    "(SOLIDARITYNODE_JOB_MAX_RUNTIME_SECONDS). No results were stored."
)


def _utc(moment: datetime | None = None) -> str:
    return (moment or datetime.now(UTC)).astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


class WorkerStoppedError(BaseException):
    """Raised in the main thread when the worker is asked to stop during a job."""


class _DbJobContext:
    def __init__(
        self, engine: Engine, job_id: uuid.UUID, kind: str, max_runtime_s: float | None
    ) -> None:
        self._engine = engine
        self._id = job_id
        self._kind = kind
        self._limit = max_runtime_s
        self._deadline = None if max_runtime_s is None else time.monotonic() + max_runtime_s

    @property
    def job_id(self) -> str:
        return str(self._id)

    def progress(self, fraction: float) -> None:
        if self._deadline is not None and time.monotonic() > self._deadline:
            assert self._limit is not None
            raise JobTimedOutError(self._kind, self._limit)
        percent = max(0.0, min(100.0, 100.0 * fraction))
        with self._engine.begin() as conn:
            cancel = conn.execute(
                text("UPDATE jobs SET progress = :p WHERE id = :id RETURNING cancel_requested"),
                {"p": percent, "id": self._id},
            ).scalar_one()
        if cancel:
            raise JobCancelledError


class _Heartbeat:
    """Renew a running job's lease (``jobs.heartbeat_at``) from a separate thread."""

    def __init__(self, engine: Engine, job_id: uuid.UUID, interval_s: float) -> None:
        self._engine = engine
        self._id = job_id
        self._interval = interval_s
        self._stop = Event()
        self._thread = Thread(target=self._loop, name=f"heartbeat-{job_id}", daemon=True)

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                with self._engine.begin() as conn:
                    conn.execute(
                        text(
                            "UPDATE jobs SET heartbeat_at = now() "
                            "WHERE id = :id AND status = 'running'"
                        ),
                        {"id": self._id},
                    )
            except Exception:  # a database hiccup must not kill the job; the next beat retries
                log.warning("job %s: heartbeat failed", self._id, exc_info=True)

    @contextlib.contextmanager
    def running(self) -> Iterator[None]:
        self._thread.start()
        try:
            yield
        finally:
            self._stop.set()
            self._thread.join()


class Worker:
    """Consume the job queue.

    Args:
        engine: Database engine.
        name: Worker name, recorded on claimed jobs and in logs only.
        handlers: Handler per job kind.
        heartbeat_s: Seconds between lease renewals of the running job.
        stale_s: A running job whose heartbeat is older than this is failed by any worker.
        max_runtime_s: Optional maximum runtime in seconds per job kind.
    """

    def __init__(
        self,
        engine: Engine,
        name: str,
        handlers: Mapping[str, Handler],
        *,
        heartbeat_s: float = 10.0,
        stale_s: float = 120.0,
        max_runtime_s: Mapping[str, float] | None = None,
    ) -> None:
        """Configure the worker."""
        self.engine = engine
        self.name = name
        self.handlers = dict(handlers)
        self.heartbeat_s = heartbeat_s
        self.stale_s = stale_s
        self.max_runtime_s = dict(max_runtime_s or {})

    def _finish(self, job_id: uuid.UUID, status: JobStatus, error: str | None) -> None:
        # Only a job that is still running is finished: if a sweep already failed it as stale,
        # that verdict stands (its results were not trusted).
        with self.engine.begin() as conn:
            result = conn.execute(
                text(
                    "UPDATE jobs SET status = :s, error = :e, finished_at = now(), "
                    "progress = CASE WHEN :s = 'succeeded' THEN 100 ELSE progress END "
                    "WHERE id = :id AND status = 'running'"
                ),
                {"s": status.value, "e": error, "id": job_id},
            )
        if result.rowcount == 0:
            log.warning("job %s was no longer running; %s not recorded", job_id, status.value)

    def fail_stale(self) -> int:
        """Mark running jobs whose heartbeat is older than ``stale_s`` as failed; return how many.

        Any worker may do this, whichever worker ran the job: its lease expired, so that worker is
        gone (killed, crashed, or cut off from the database).
        """
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    "SELECT id, worker, coalesce(heartbeat_at, started_at) AS beat FROM jobs "
                    "WHERE status = 'running' AND coalesce(heartbeat_at, started_at) "
                    "< now() - make_interval(secs => :stale) FOR UPDATE SKIP LOCKED"
                ),
                {"stale": self.stale_s},
            ).all()
            for row in rows:
                when = f"no heartbeat since {_utc(row.beat)}" if row.beat else "never started"
                conn.execute(
                    text(
                        "UPDATE jobs SET status = 'failed', error = :e, finished_at = now() "
                        "WHERE id = :id"
                    ),
                    {
                        "e": INTERRUPTED.format(worker=row.worker or "unknown", when=when),
                        "id": row.id,
                    },
                )
                log.warning("job %s of worker %s failed as stale (%s)", row.id, row.worker, when)
        return len(rows)

    def claim(self) -> tuple[uuid.UUID, str, dict[str, Any]] | None:
        """Claim the oldest queued job, or return ``None``."""
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    "SELECT id, kind, payload FROM jobs WHERE status = 'queued' "
                    "ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED"
                )
            ).one_or_none()
            if row is None:
                return None
            conn.execute(
                text(
                    "UPDATE jobs SET status = 'running', worker = :w, started_at = now(), "
                    "heartbeat_at = now(), progress = 0 WHERE id = :id"
                ),
                {"w": self.name, "id": row.id},
            )
        # The claim transaction has committed here: the job runs with no transaction or row lock
        # held (ADR 0006), so the API can read and flag it and a sweep can fail it.
        return row.id, row.kind, dict(row.payload)

    def run_once(self) -> bool:
        """Run one queued job if there is one; return whether a job was run."""
        claimed = self.claim()
        if claimed is None:
            return False
        self.execute(*claimed)
        return True

    def execute(self, job_id: uuid.UUID, kind: str, payload: Mapping[str, Any]) -> None:
        """Run one claimed job with its handler and record the final state."""
        handler = self.handlers.get(kind)
        if handler is None:
            self._finish(job_id, JobStatus.FAILED, f"no handler for job kind {kind!r}")
            return
        log.info("job %s (%s) started by %s", job_id, kind, self.name)
        ctx = _DbJobContext(self.engine, job_id, kind, self.max_runtime_s.get(kind))
        try:
            with _Heartbeat(self.engine, job_id, self.heartbeat_s).running():
                handler(ctx, payload)
        except JobTimedOutError as exc:
            message = TIMED_OUT.format(limit=exc.limit_s, kind=exc.kind)
            self._finish(job_id, JobStatus.FAILED, message)
            log.warning("job %s stopped: over the maximum runtime of %g s", job_id, exc.limit_s)
        except JobCancelledError:
            self._finish(job_id, JobStatus.CANCELLED, "Cancelled by a user while running.")
            log.info("job %s cancelled", job_id)
        except WorkerStoppedError:
            self._finish(
                job_id, JobStatus.FAILED, INTERRUPTED.format(worker=self.name, when=_utc())
            )
            log.warning("job %s interrupted by worker stop", job_id)
            raise
        except Exception as exc:
            log.exception("job %s failed", job_id)
            self._finish(job_id, JobStatus.FAILED, f"{type(exc).__name__}: {exc}")
        else:
            self._finish(job_id, JobStatus.SUCCEEDED, None)
            log.info("job %s succeeded", job_id)

    def run_until_idle(self) -> int:
        """Run queued jobs until the queue is empty; return how many ran (tests, CLI)."""
        count = 0
        while self.run_once():
            count += 1
        return count

    def serve(self, stop: Event, poll_s: float) -> None:
        """Poll the queue until ``stop`` is set, failing stale jobs every ``heartbeat_s``."""
        last_sweep = float("-inf")
        while not stop.is_set():
            if time.monotonic() - last_sweep >= self.heartbeat_s:
                self.fail_stale()
                last_sweep = time.monotonic()
            if not self.run_once():
                stop.wait(poll_s)


def build_worker(settings: Settings, engine: Engine | None = None) -> Worker:
    """Return a worker with the platform's handlers."""
    engine = engine or create_engine(settings.database_url.get_secret_value(), pool_pre_ping=True)
    return Worker(
        engine,
        settings.worker_name,
        {RUN_JOB_KIND: partial(execute_run, engine, settings)},
        heartbeat_s=settings.job_heartbeat_seconds,
        stale_s=settings.job_stale_seconds,
        max_runtime_s=settings.max_runtimes(),
    )


def main() -> int:
    """Entry point of the worker service."""
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    worker = build_worker(settings)
    try:
        check_role(worker.engine, settings.deployment_mode)
    except RoleMismatchError as exc:
        log.error("%s", exc)
        return 2
    stop = Event()

    def on_signal(signum: int, _frame: FrameType | None) -> None:
        log.info("signal %s: stopping", signum)
        stop.set()
        raise WorkerStoppedError

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    recovered = worker.fail_stale()
    if recovered:
        log.warning("marked %d interrupted job(s) as failed", recovered)
    log.info("worker %s ready (queue: PostgreSQL)", settings.worker_name)
    with contextlib.suppress(WorkerStoppedError):
        worker.serve(stop, settings.worker_poll_s)
    log.info("worker %s stopped", settings.worker_name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
