"""Run provenance: seed source, execution environment, refused cached reuse (ADR 0017).

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-25

* ``runs.seed_source``: ``given`` (by the user or the platform, for example the baseline's 1) or
  ``drawn`` (none was given, so one was drawn and recorded).
* ``runs.environment``: Python, NumPy and platform versions of the worker that executed the run
  (recorded for reproducibility, not part of the input hash).
* ``runs.reuse_refused``: why a matching earlier run was not reused (its samples file was
  missing or failed its SHA-256 check), so the run page can say so.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the provenance columns."""
    op.execute(
        "ALTER TABLE runs ADD COLUMN seed_source text NOT NULL DEFAULT 'given' "
        "CHECK (seed_source IN ('given', 'drawn'))"
    )
    op.execute("ALTER TABLE runs ADD COLUMN environment jsonb")
    op.execute("ALTER TABLE runs ADD COLUMN reuse_refused text")


def downgrade() -> None:
    """Drop the provenance columns."""
    op.execute("ALTER TABLE runs DROP COLUMN reuse_refused")
    op.execute("ALTER TABLE runs DROP COLUMN environment")
    op.execute("ALTER TABLE runs DROP COLUMN seed_source")
