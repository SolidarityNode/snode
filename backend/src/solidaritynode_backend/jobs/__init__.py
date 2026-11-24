"""Background jobs: a minimal interface and an in-process implementation.

Long-running simulations run as background jobs, never inside a request handler (AGENTS.md).
The production queue (for example a database-backed queue, RQ, Celery, Dramatiq or Arq) is
**not chosen**: see ADR 0006. Callers depend only on :class:`JobRunner`.
"""

from solidaritynode_backend.jobs.base import JobInfo, JobRunner, JobStatus
from solidaritynode_backend.jobs.inprocess import InProcessJobRunner

__all__ = ["InProcessJobRunner", "JobInfo", "JobRunner", "JobStatus"]
