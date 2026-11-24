"""Background worker: claims jobs from the PostgreSQL queue and runs them (ADR 0006).

Runs as its own compose service (``python -m solidaritynode_backend.worker``). One job at a time:

* claims the oldest queued job with ``SELECT … FOR UPDATE SKIP LOCKED``;
* reports progress to the job row; a cancel request stops the job at its next progress step;
* on ``SIGTERM``/``SIGINT`` (for example ``make stop SERVICE=worker``) it marks the running job
  failed with a clear message and exits;
* on start it marks jobs it was running when it died (for example after ``SIGKILL``) as failed.
"""

from __future__ import annotations

import contextlib
import logging
import signal
import sys
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from functools import partial
from threading import Event
from types import FrameType
from typing import Any

from sqlalchemy import Engine, create_engine, text

from solidaritynode_backend.config import Settings, get_settings
from solidaritynode_backend.jobs import JobCancelledError, JobContext, JobStatus
from solidaritynode_backend.services.runs import RUN_JOB_KIND, execute_run

__all__ = ["Handler", "Worker", "WorkerStoppedError", "main"]

log = logging.getLogger("solidaritynode.worker")

type Handler = Callable[[JobContext, Mapping[str, Any]], None]

INTERRUPTED = (
    "Interrupted: the worker ({worker}) stopped while this run was running ({when}). "
    "No results were stored. Start the run again."
)


class WorkerStoppedError(BaseException):
    """Raised in the main thread when the worker is asked to stop during a job."""


class _DbJobContext:
    def __init__(self, engine: Engine, job_id: uuid.UUID) -> None:
        self._engine = engine
        self._id = job_id

    @property
    def job_id(self) -> str:
        return str(self._id)

    def progress(self, fraction: float) -> None:
        percent = max(0.0, min(100.0, 100.0 * fraction))
        with self._engine.begin() as conn:
            cancel = conn.execute(
                text("UPDATE jobs SET progress = :p WHERE id = :id RETURNING cancel_requested"),
                {"p": percent, "id": self._id},
            ).scalar_one()
        if cancel:
            raise JobCancelledError


class Worker:
    """Consume the job queue.

    Args:
        engine: Database engine.
        name: Worker name recorded on claimed jobs (used to recover them after a crash).
        handlers: Handler per job kind.
    """

    def __init__(self, engine: Engine, name: str, handlers: Mapping[str, Handler]) -> None:
        """Configure the worker."""
        self.engine = engine
        self.name = name
        self.handlers = dict(handlers)

    def _finish(self, job_id: uuid.UUID, status: JobStatus, error: str | None) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE jobs SET status = :s, error = :e, finished_at = now(), "
                    "progress = CASE WHEN :s = 'succeeded' THEN 100 ELSE progress END "
                    "WHERE id = :id"
                ),
                {"s": status.value, "e": error, "id": job_id},
            )

    def recover(self) -> int:
        """Mark jobs this worker was running when it stopped as failed; return how many."""
        when = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
        with self.engine.begin() as conn:
            result = conn.execute(
                text(
                    "UPDATE jobs SET status = 'failed', error = :e, finished_at = now() "
                    "WHERE status = 'running' AND worker = :w"
                ),
                {
                    "e": INTERRUPTED.format(worker=self.name, when=f"found at restart {when}"),
                    "w": self.name,
                },
            )
        return result.rowcount

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
                    "progress = 0 WHERE id = :id"
                ),
                {"w": self.name, "id": row.id},
            )
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
        log.info("job %s (%s) started", job_id, kind)
        try:
            handler(_DbJobContext(self.engine, job_id), payload)
        except JobCancelledError:
            self._finish(job_id, JobStatus.CANCELLED, "Cancelled by a user while running.")
            log.info("job %s cancelled", job_id)
        except WorkerStoppedError:
            when = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
            self._finish(job_id, JobStatus.FAILED, INTERRUPTED.format(worker=self.name, when=when))
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
        """Poll the queue until ``stop`` is set."""
        while not stop.is_set():
            if not self.run_once():
                stop.wait(poll_s)


def build_worker(settings: Settings, engine: Engine | None = None) -> Worker:
    """Return a worker with the platform's handlers."""
    engine = engine or create_engine(settings.database_url.get_secret_value(), pool_pre_ping=True)
    return Worker(
        engine, settings.worker_name, {RUN_JOB_KIND: partial(execute_run, engine, settings)}
    )


def main() -> int:
    """Entry point of the worker service."""
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    worker = build_worker(settings)
    stop = Event()

    def on_signal(signum: int, _frame: FrameType | None) -> None:
        log.info("signal %s: stopping", signum)
        stop.set()
        raise WorkerStoppedError

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    recovered = worker.recover()
    if recovered:
        log.warning("marked %d interrupted job(s) as failed", recovered)
    log.info("worker %s ready (queue: PostgreSQL)", settings.worker_name)
    with contextlib.suppress(WorkerStoppedError):
        worker.serve(stop, settings.worker_poll_s)
    log.info("worker %s stopped", settings.worker_name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
