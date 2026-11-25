"""One name for the verified state: coverage ``verified`` becomes ``verified_by_municipality``.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-25

Feature quality already used ``verified_by_municipality``; layer coverage used ``verified``.
Both now use ``verified_by_municipality`` (ADR 0013). Stored manifests keep the text they were
imported with; ``data_coverage`` rows are renamed.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename coverage status ``verified``."""
    op.execute("ALTER TABLE data_coverage DROP CONSTRAINT data_coverage_status_check")
    op.execute(
        "UPDATE data_coverage SET status = 'verified_by_municipality' WHERE status = 'verified'"
    )
    op.execute(
        "ALTER TABLE data_coverage ADD CONSTRAINT data_coverage_status_check CHECK "
        "(status IN ('missing', 'open_data', 'estimated', 'verified_by_municipality'))"
    )


def downgrade() -> None:
    """Rename it back."""
    op.execute("ALTER TABLE data_coverage DROP CONSTRAINT data_coverage_status_check")
    op.execute(
        "UPDATE data_coverage SET status = 'verified' WHERE status = 'verified_by_municipality'"
    )
    op.execute(
        "ALTER TABLE data_coverage ADD CONSTRAINT data_coverage_status_check CHECK "
        "(status IN ('missing', 'open_data', 'estimated', 'verified'))"
    )
