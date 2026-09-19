"""invocation outcome table

Revision ID: f7a8b9c0d1e2
Revises: e5f1a2c3d4b6
Create Date: 2026-09-21 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

from devin_flow.outcomes import derive_outcome_kinds

# revision identifiers, used by Alembic.
revision: str = "f7a8b9c0d1e2"
down_revision: str | Sequence[str] | None = "e5f1a2c3d4b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "invocation_outcome",
        sa.Column("invocation_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(
            ["invocation_id"],
            ["invocation.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("invocation_id", "kind"),
    )
    invocation = sa.table(
        "invocation",
        sa.column("id", sa.Uuid()),
        sa.column("pull_requests", sa.JSON()),
        sa.column("structured_output", sa.JSON()),
    )
    invocation_outcome = sa.table(
        "invocation_outcome",
        sa.column("invocation_id", sa.Uuid()),
        sa.column("kind", sqlmodel.sql.sqltypes.AutoString()),
    )
    connection = op.get_bind()
    rows = [
        {"invocation_id": invocation_id, "kind": kind}
        for invocation_id, pull_requests, structured_output in connection.execute(
            sa.select(
                invocation.c.id,
                invocation.c.pull_requests,
                invocation.c.structured_output,
            )
        )
        for kind in derive_outcome_kinds(pull_requests or [], structured_output)
    ]
    if rows:
        connection.execute(sa.insert(invocation_outcome), rows)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("invocation_outcome")
