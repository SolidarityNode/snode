"""Samples file integrity and size estimate on runs (ADR 0008).

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-25

* ``runs.samples_sha256``: SHA-256 of the run's samples Parquet file, verified on read and export.
  NULL for runs stored before this migration (their files are not checked).
* ``runs.samples_estimate_bytes`` and ``runs.samples_limit_bytes``: the estimated size of the
  samples file and the warning limit in force when the run was created.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the checksum and size-estimate columns."""
    op.execute("ALTER TABLE runs ADD COLUMN samples_sha256 text")
    op.execute("ALTER TABLE runs ADD COLUMN samples_estimate_bytes bigint")
    op.execute("ALTER TABLE runs ADD COLUMN samples_limit_bytes bigint")


def downgrade() -> None:
    """Drop the checksum and size-estimate columns."""
    op.execute("ALTER TABLE runs DROP COLUMN samples_limit_bytes")
    op.execute("ALTER TABLE runs DROP COLUMN samples_estimate_bytes")
    op.execute("ALTER TABLE runs DROP COLUMN samples_sha256")
