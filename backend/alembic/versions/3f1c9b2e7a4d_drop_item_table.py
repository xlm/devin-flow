"""drop item table

Revision ID: 3f1c9b2e7a4d
Revises: dba54d520a2a
Create Date: 2026-09-19 07:55:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3f1c9b2e7a4d"
down_revision: str | Sequence[str] | None = "dba54d520a2a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index(op.f("ix_item_name"), table_name="item")
    op.drop_table("item")


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table(
        "item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_item_name"), "item", ["name"], unique=True)
