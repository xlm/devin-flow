"""action node enabled state

Revision ID: 1c6a8b9d2e7f
Revises: 48aaca2bd368
Create Date: 2026-09-19 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1c6a8b9d2e7f"
down_revision: str | Sequence[str] | None = "48aaca2bd368"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "action_node",
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("action_node", "enabled")
