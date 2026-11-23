"""Initial empty migration.

Revision ID: 0001
Revises:
Create Date: 2026-11-24

No tables yet. The PostGIS extension is created by the database image in the configured
database. Ticket tables wait for ADR 0010 (OQ-21).
"""

from collections.abc import Sequence

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Nothing to create yet."""


def downgrade() -> None:
    """Nothing to drop."""
