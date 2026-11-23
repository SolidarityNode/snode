"""Job runner interface (ADR 0006 open)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

__all__ = ["JobInfo", "JobRunner", "JobStatus"]


class JobStatus(StrEnum):
    """Lifecycle of a job."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class JobInfo:
    """Snapshot of a job.

    Attributes:
        id: Opaque job identifier.
        name: Human-readable job name.
        status: Current status.
        error: Error message if the job failed.
    """

    id: str
    name: str
    status: JobStatus
    error: str | None = None


class JobRunner(Protocol):
    """Submit callables to run outside the request cycle and query their status."""

    def submit(self, name: str, fn: Callable[[], object]) -> str:
        """Schedule ``fn`` and return its job id immediately."""
        ...

    def info(self, job_id: str) -> JobInfo:
        """Return the current status of a job.

        Raises:
            KeyError: If the job id is unknown.
        """
        ...

    def shutdown(self, wait: bool = True) -> None:
        """Stop accepting jobs and release resources."""
        ...
