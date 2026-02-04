"""Add room_description column to rooms table

Revision ID: 007
Revises: 006_customer_data_retention
Create Date: 2026-02-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '007_add_room_description'
down_revision: Union[str, None] = '006_customer_data_retention'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add room_description column to rooms table."""
    op.add_column('rooms', sa.Column('room_description', sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove room_description column from rooms table."""
    op.drop_column('rooms', 'room_description')
