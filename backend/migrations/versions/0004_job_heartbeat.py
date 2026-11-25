"""Job lease: ``jobs.heartbeat_at`` (ADR 0006).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-25

A running job's worker updates ``heartbeat_at`` every few seconds. Any worker marks running jobs
whose heartbeat is too old as failed, so recovery no longer depends on the worker's name.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the heartbeat column and an index for the stale-job sweep."""
    op.execute("ALTER TABLE jobs ADD COLUMN heartbeat_at timestamptz")
    op.execute("UPDATE jobs SET heartbeat_at = started_at WHERE status = 'running'")
    op.execute(
        "CREATE INDEX jobs_running_heartbeat ON jobs (heartbeat_at) WHERE status = 'running'"
    )


def downgrade() -> None:
    """Remove the heartbeat column."""
    op.execute("DROP INDEX IF EXISTS jobs_running_heartbeat")
    op.execute("ALTER TABLE jobs DROP COLUMN IF EXISTS heartbeat_at")
