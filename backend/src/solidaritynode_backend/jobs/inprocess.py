"""In-process job runner on a thread pool. For development and tests only.

Jobs are lost when the process stops and results are not stored. A durable queue replaces this
after ADR 0006.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor

from solidaritynode_backend.jobs.base import JobInfo, JobStatus

__all__ = ["InProcessJobRunner"]


class InProcessJobRunner:
    """Run jobs on a local :class:`~concurrent.futures.ThreadPoolExecutor`.

    Args:
        max_workers: Maximum concurrent jobs.
    """

    def __init__(self, max_workers: int = 2) -> None:
        """Create the pool."""
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="job")
        self._jobs: dict[str, tuple[str, Future[object]]] = {}
        self._started: set[str] = set()
        self._lock = threading.Lock()

    def submit(self, name: str, fn: Callable[[], object]) -> str:
        """Schedule ``fn`` and return its job id."""
        job_id = uuid.uuid4().hex

        def wrapped() -> object:
            with self._lock:
                self._started.add(job_id)
            return fn()

        future = self._executor.submit(wrapped)
        with self._lock:
            self._jobs[job_id] = (name, future)
        return job_id

    def info(self, job_id: str) -> JobInfo:
        """Return the job status."""
        with self._lock:
            name, future = self._jobs[job_id]
            started = job_id in self._started
        if not future.done():
            status = JobStatus.RUNNING if started else JobStatus.PENDING
            return JobInfo(job_id, name, status)
        error = future.exception()
        if error is not None:
            return JobInfo(job_id, name, JobStatus.FAILED, repr(error))
        return JobInfo(job_id, name, JobStatus.SUCCEEDED)

    def shutdown(self, wait: bool = True) -> None:
        """Shut the pool down."""
        self._executor.shutdown(wait=wait)
