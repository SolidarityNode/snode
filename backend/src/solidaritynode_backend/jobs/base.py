"""Job interface (ADR 0006, accepted for v0.1, to be revisited).

Evolved from the bootstrap interface: a job is a ``kind`` plus a JSON payload (not a Python
callable), so it can cross process boundaries; jobs can be cancelled; handlers report progress
through a :class:`JobContext`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

__all__ = ["JobCancelledError", "JobContext", "JobInfo", "JobRunner", "JobStatus"]


class JobStatus(StrEnum):
    """Lifecycle of a job: ``queued → running → succeeded | failed | cancelled``."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def finished(self) -> bool:
        """Return whether the job reached a final state."""
        return self in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED)


@dataclass(frozen=True, slots=True)
class JobInfo:
    """Snapshot of a job.

    Attributes:
        id: Job id.
        kind: Handler name, for example ``run``.
        status: Current status.
        progress: Percent complete, 0–100.
        error: Error message if the job failed or was cancelled.
        cancel_requested: Whether cancellation was asked for while running.
        created_at: When it was queued.
        started_at: When a worker picked it up.
        finished_at: When it reached a final state.
    """

    id: str
    kind: str
    status: JobStatus
    progress: float
    error: str | None
    cancel_requested: bool
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class JobCancelledError(Exception):
    """Raised inside a handler when its job was cancelled."""


class JobTimedOutError(JobCancelledError):
    """Raised inside a handler when its job ran longer than the maximum runtime of its kind.

    A subclass of :class:`JobCancelledError`, so a handler that cleans up on cancel also cleans up
    here; the worker records the job as failed, not cancelled.
    """

    def __init__(self, kind: str, limit_s: float) -> None:
        """Record the job kind and its limit in seconds."""
        super().__init__(kind, limit_s)
        self.kind = kind
        self.limit_s = limit_s


class JobContext(Protocol):
    """What a running handler can do."""

    @property
    def job_id(self) -> str:
        """The job's id."""
        ...

    def progress(self, fraction: float) -> None:
        """Report ``fraction`` (0–1) done; raises :class:`JobCancelledError` if cancelled."""
        ...


class JobRunner(Protocol):
    """Submit jobs to run outside the request cycle, query and cancel them."""

    def submit(self, kind: str, payload: Mapping[str, Any]) -> str:
        """Queue a job and return its id immediately."""
        ...

    def info(self, job_id: str) -> JobInfo:
        """Return the job's status.

        Raises:
            KeyError: If the job id is unknown.
        """
        ...

    def cancel(self, job_id: str) -> JobInfo:
        """Cancel a queued job at once; ask a running job to stop at its next progress step."""
        ...
