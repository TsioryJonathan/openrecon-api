"""add owner_id to investigations

Revision ID: c3f9a1e5b7d2
Revises: a119b6af3179
Create Date: 2026-09-22 17:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3f9a1e5b7d2'
down_revision: Union[str, Sequence[str], None] = 'a119b6af3179'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Idempotent: only add owner_id if this DB predates the column.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("investigations")}
    if "owner_id" not in columns:
        op.add_column('investigations', sa.Column('owner_id', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("investigations")}
    if "owner_id" in columns:
        op.drop_column('investigations', 'owner_id')
