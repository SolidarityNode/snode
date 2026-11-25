"""Result statistics: mean, median and interval quantiles per result value (ADR 0017).

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-25

``run_results.value`` (the model's central value, a mean) becomes ``mean``, and ``median`` is
added; ``low`` and ``high`` stay the interval bounds, at the quantile levels recorded in the
run configuration (``interval_quantiles``, default 5 % and 95 %).

Rows of earlier runs: deterministic values (``low = high = mean``) get ``median = mean``. Sampled
values keep ``median`` NULL ("not available"): runs are immutable, so their samples are not
re-read here; start such a run again to get its median.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename ``value`` to ``mean``, add ``median`` and fill it for deterministic values."""
    op.execute("ALTER TABLE run_results RENAME COLUMN value TO mean")
    op.execute("ALTER TABLE run_results ADD COLUMN median double precision")
    op.execute("UPDATE run_results SET median = mean WHERE low = mean AND high = mean")


def downgrade() -> None:
    """Drop ``median`` and rename ``mean`` back to ``value``."""
    op.execute("ALTER TABLE run_results DROP COLUMN median")
    op.execute("ALTER TABLE run_results RENAME COLUMN mean TO value")
