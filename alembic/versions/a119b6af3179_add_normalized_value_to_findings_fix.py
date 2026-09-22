"""add normalized_value to findings (fix)

Revision ID: a119b6af3179
Revises: 4dbaf8718c46
Create Date: 2026-09-22 11:17:54.380770

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a119b6af3179'
down_revision: Union[str, Sequence[str], None] = '4dbaf8718c46'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Idempotent: the initial schema (332d793e375d) already creates
    # normalized_value + ix_findings_dedup. Only add each if missing.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("findings")}
    if "normalized_value" not in columns:
        op.add_column('findings', sa.Column('normalized_value', sa.String(), nullable=True))
    indexes = {i["name"] for i in inspector.get_indexes("findings")}
    if "ix_findings_dedup" not in indexes:
        op.create_index('ix_findings_dedup', 'findings', ['target_id', 'type', 'normalized_value'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {i["name"] for i in inspector.get_indexes("findings")}
    if "ix_findings_dedup" in indexes:
        op.drop_index('ix_findings_dedup', table_name='findings')
    columns = {c["name"] for c in inspector.get_columns("findings")}
    if "normalized_value" in columns:
        op.drop_column('findings', 'normalized_value')
