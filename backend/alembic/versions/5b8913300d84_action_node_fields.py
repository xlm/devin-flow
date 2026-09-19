"""action node fields

Revision ID: 5b8913300d84
Revises: 7ee7af480f0b
Create Date: 2026-09-19 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5b8913300d84"
down_revision: str | Sequence[str] | None = "7ee7af480f0b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "action_node",
        sa.Column(
            "name",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "action_node",
        sa.Column(
            "extra_instructions",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "action_node",
        sa.Column(
            "playbook_id",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("action_node", "playbook_id")
    op.drop_column("action_node", "extra_instructions")
    op.drop_column("action_node", "name")
