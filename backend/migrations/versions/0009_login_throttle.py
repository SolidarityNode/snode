"""Login throttling state (ADR 0015).

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-25

One row per throttled key: ``kind`` is ``account`` or ``address``; ``key_hash`` is the SHA-256
of the username (lower-cased) or of the client address, so neither attempted usernames (which
may contain mistyped passwords) nor addresses are stored in clear. Rows older than the lock
window are deleted on later sign-ins.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create ``login_throttle``."""
    op.execute(
        """
        CREATE TABLE login_throttle (
            kind text NOT NULL CHECK (kind IN ('account', 'address')),
            key_hash text NOT NULL,
            failures integer NOT NULL DEFAULT 0,
            last_failure_at timestamptz NOT NULL,
            next_allowed_at timestamptz NOT NULL,
            locked_until timestamptz,
            PRIMARY KEY (kind, key_hash)
        )"""
    )


def downgrade() -> None:
    """Drop ``login_throttle``."""
    op.execute("DROP TABLE login_throttle")
