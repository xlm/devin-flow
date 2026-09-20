"""invocation outcome table

Revision ID: f7a8b9c0d1e2
Revises: a1f3e5c7d9b2
Create Date: 2026-09-21 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import context, op

from devin_flow.outcomes import STRUCTURED_OUTCOMES, derive_outcome_kinds

# revision identifiers, used by Alembic.
revision: str = "f7a8b9c0d1e2"
down_revision: str | Sequence[str] | None = "a1f3e5c7d9b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Postgres-only equivalent of the Python backfill below, so that offline
# upgrades (--sql) still populate the link table. pull_requests is json,
# not jsonb. json_typeof(NULL) is NULL, so NULL structured_output rows are
# excluded implicitly; the object check keeps JSON array/scalar values
# from erroring on ->.
OFFLINE_BACKFILL_SQL = f"""
INSERT INTO invocation_outcome (invocation_id, kind)
SELECT id, 'pull_request' FROM invocation
WHERE EXISTS (
    SELECT 1 FROM json_array_elements(pull_requests) AS pr
    WHERE json_typeof(pr -> 'pr_url') = 'string' AND pr ->> 'pr_url' <> ''
)
UNION
SELECT id, structured_output ->> 'outcome' FROM invocation
WHERE json_typeof(structured_output) = 'object'
  AND json_typeof(structured_output -> 'outcome') = 'string'
  AND structured_output ->> 'outcome' IN (
    {", ".join(f"'{kind}'" for kind in sorted(STRUCTURED_OUTCOMES))}
  )
"""


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
    if context.is_offline_mode():
        op.execute(OFFLINE_BACKFILL_SQL)
        return
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
