"""trigger node event and repository

Revision ID: 55a757d09d4e
Revises: 7ee7af480f0b
Create Date: 2026-09-19 11:13:40.247363

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "55a757d09d4e"
down_revision: str | Sequence[str] | None = "7ee7af480f0b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "trigger_node",
        sa.Column("event_action", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.add_column(
        "trigger_node",
        sa.Column(
            "repository_full_name",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("trigger_node", "repository_full_name")
    op.drop_column("trigger_node", "event_action")
