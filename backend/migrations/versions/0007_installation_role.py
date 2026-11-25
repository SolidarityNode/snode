"""Installation role lock (ADR 0012).

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-25

Table ``installation`` holds exactly one row: the deployment role (``municipality`` or ``hub``)
recorded when the database is first initialised, from ``DEPLOYMENT_MODE``. The API, the worker
and the CLI refuse to start when ``DEPLOYMENT_MODE`` differs from it
(:mod:`solidaritynode_backend.services.installation`). Later migrations that create tables of
one role only read it with
:func:`solidaritynode_backend.services.installation.stored_role`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from solidaritynode_backend.config import get_settings

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the one-row ``installation`` table with the role in ``DEPLOYMENT_MODE``."""
    op.execute(
        """
        CREATE TABLE installation (
            id smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
            deployment_mode text NOT NULL CHECK (deployment_mode IN ('municipality', 'hub')),
            initialised_at timestamptz NOT NULL DEFAULT now()
        )"""
    )
    op.get_bind().execute(
        sa.text("INSERT INTO installation (deployment_mode) VALUES (:mode)"),
        {"mode": get_settings().deployment_mode},
    )


def downgrade() -> None:
    """Drop the role lock."""
    op.execute("DROP TABLE installation")
