"""Background jobs: the :class:`JobRunner` interface, a PostgreSQL queue and the worker.

Long-running simulations run as background jobs, never inside a request handler (AGENTS.md).
v0.1 uses a queue in PostgreSQL (``SELECT … FOR UPDATE SKIP LOCKED``) consumed by a separate
worker process (ADR 0006, accepted for v0.1, to be revisited). Routers depend only on
:class:`JobRunner`, so the queue can change without touching them.
"""

from solidaritynode_backend.jobs.base import (
    JobCancelledError,
    JobContext,
    JobInfo,
    JobRunner,
    JobStatus,
)
from solidaritynode_backend.jobs.postgres import PostgresJobRunner

__all__ = [
    "JobCancelledError",
    "JobContext",
    "JobInfo",
    "JobRunner",
    "JobStatus",
    "PostgresJobRunner",
]
