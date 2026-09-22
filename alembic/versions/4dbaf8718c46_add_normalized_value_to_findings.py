"""add normalized_value to findings

Revision ID: 4dbaf8718c46
Revises: 332d793e375d
Create Date: 2026-09-22 10:44:10.057781

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4dbaf8718c46'
down_revision: Union[str, Sequence[str], None] = '332d793e375d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("findings", sa.Column("normalized_value", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("findings", "normalized_value")
