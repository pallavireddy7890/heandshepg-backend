"""add_inactive_at_to_properties

Revision ID: 9d7807cbcb6e
Revises: 8491d42b66d8
Create Date: 2026-06-08 13:01:05.046872

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '9d7807cbcb6e'
down_revision: Union[str, None] = '8491d42b66d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('properties', sa.Column('inactive_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('properties', 'inactive_at')
