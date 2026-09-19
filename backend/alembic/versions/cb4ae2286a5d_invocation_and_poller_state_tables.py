"""invocation and poller state tables

Revision ID: cb4ae2286a5d
Revises: 1c6a8b9d2e7f
Create Date: 2026-09-19 13:25:05.281340

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cb4ae2286a5d"
down_revision: str | Sequence[str] | None = "1c6a8b9d2e7f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "poller_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "invocation",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("automation_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("action_node_id", sa.Uuid(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("url", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("pull_requests", sa.JSON(), nullable=False),
        sa.Column("structured_output", sa.JSON(), nullable=True),
        sa.Column("session_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["action_node_id"],
            ["action_node.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id"),
    )
    op.create_index(
        op.f("ix_invocation_action_node_id"),
        "invocation",
        ["action_node_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_invocation_automation_id"),
        "invocation",
        ["automation_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_invocation_automation_id"), table_name="invocation")
    op.drop_index(op.f("ix_invocation_action_node_id"), table_name="invocation")
    op.drop_table("invocation")
    op.drop_table("poller_state")
