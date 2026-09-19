"""edge uniqueness indexes

Revision ID: 7ee7af480f0b
Revises: cb8d638d9582
Create Date: 2026-09-19 08:32:20.007709

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7ee7af480f0b"
down_revision: str | Sequence[str] | None = "cb8d638d9582"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        "ux_edge_pair",
        "edge",
        ["source_id", "target_id"],
        unique=True,
    )
    op.create_index(
        "ux_edge_trigger_source",
        "edge",
        ["source_id"],
        unique=True,
        postgresql_where=sa.text("source_kind = 'trigger'"),
        sqlite_where=sa.text("source_kind = 'trigger'"),
    )
    op.create_index(
        "ux_edge_trigger_target",
        "edge",
        ["target_id"],
        unique=True,
        postgresql_where=sa.text("source_kind = 'trigger'"),
        sqlite_where=sa.text("source_kind = 'trigger'"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ux_edge_trigger_target",
        table_name="edge",
        postgresql_where=sa.text("source_kind = 'trigger'"),
        sqlite_where=sa.text("source_kind = 'trigger'"),
    )
    op.drop_index(
        "ux_edge_trigger_source",
        table_name="edge",
        postgresql_where=sa.text("source_kind = 'trigger'"),
        sqlite_where=sa.text("source_kind = 'trigger'"),
    )
    op.drop_index(
        "ux_edge_pair",
        table_name="edge",
    )
