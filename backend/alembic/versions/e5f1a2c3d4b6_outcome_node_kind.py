"""outcome node kind

Revision ID: e5f1a2c3d4b6
Revises: cb4ae2286a5d
Create Date: 2026-09-19 14:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f1a2c3d4b6"
down_revision: str | Sequence[str] | None = "cb4ae2286a5d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "outcome_node",
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("outcome_node", "kind")
