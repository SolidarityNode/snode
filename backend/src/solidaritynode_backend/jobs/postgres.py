"""PostgreSQL-backed job queue (ADR 0006, accepted for v0.1, to be revisited).

Jobs are rows in table ``jobs``. :class:`PostgresJobRunner` only writes rows; the worker
(:mod:`solidaritynode_backend.worker`) claims them with ``SELECT … FOR UPDATE SKIP LOCKED``.
The runner works on the caller's session, so a job can be queued in the same transaction as the
record that needs it (for example a run).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import update
from sqlalchemy.orm import Session

from solidaritynode_backend.jobs.base import JobInfo, JobStatus
from solidaritynode_backend.messages import msg
from solidaritynode_backend.orm import Job

__all__ = ["PostgresJobRunner", "job_info"]


def job_info(job: Job) -> JobInfo:
    """Convert a job row to a :class:`JobInfo`."""
    return JobInfo(
        id=str(job.id),
        kind=job.kind,
        status=JobStatus(job.status),
        progress=job.progress,
        error=job.error,
        cancel_requested=job.cancel_requested,
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


class PostgresJobRunner:
    """Queue jobs in PostgreSQL on the given session (the caller commits)."""

    def __init__(self, db: Session) -> None:
        """Use ``db`` for every operation."""
        self._db = db

    def submit(self, kind: str, payload: Mapping[str, Any]) -> str:
        """Insert a queued job and return its id."""
        job = Job(id=uuid.uuid4(), kind=kind, payload=dict(payload), status=JobStatus.QUEUED)
        self._db.add(job)
        self._db.flush()
        return str(job.id)

    def info(self, job_id: str) -> JobInfo:
        """Return the job's status."""
        job = self._db.get(Job, uuid.UUID(job_id))
        if job is None:
            raise KeyError(job_id)
        self._db.refresh(job)
        return job_info(job)

    def cancel(self, job_id: str) -> JobInfo:
        """Cancel a queued job, or flag a running one; finished jobs are left unchanged."""
        jid = uuid.UUID(job_id)
        self._db.execute(
            update(Job)
            .where(Job.id == jid, Job.status == JobStatus.QUEUED)
            .values(
                status=JobStatus.CANCELLED,
                error=msg("run.cancelled_queued"),
                finished_at=datetime.now(UTC),
            )
        )
        self._db.execute(
            update(Job)
            .where(Job.id == jid, Job.status == JobStatus.RUNNING)
            .values(cancel_requested=True)
        )
        self._db.flush()
        return self.info(job_id)
