"""action node archived at

Revision ID: a1f3e5c7d9b2
Revises: e5f1a2c3d4b6
Create Date: 2026-09-20 10:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1f3e5c7d9b2"
down_revision: str | Sequence[str] | None = "e5f1a2c3d4b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column("action_node", "deleted_at", new_column_name="archived_at")


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column("action_node", "archived_at", new_column_name="deleted_at")
