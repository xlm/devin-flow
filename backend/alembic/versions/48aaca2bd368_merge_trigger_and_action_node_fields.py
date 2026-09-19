"""merge trigger and action node fields

Revision ID: 48aaca2bd368
Revises: 55a757d09d4e, 5b8913300d84
Create Date: 2026-09-19 11:48:07.181642

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "48aaca2bd368"
down_revision: str | Sequence[str] | None = ("55a757d09d4e", "5b8913300d84")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
