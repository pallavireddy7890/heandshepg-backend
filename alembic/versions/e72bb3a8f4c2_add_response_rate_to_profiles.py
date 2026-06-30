"""add_response_rate_to_profiles

Revision ID: e72bb3a8f4c2
Revises: 9d7807cbcb6e
Create Date: 2026-06-30 12:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e72bb3a8f4c2'
down_revision: Union[str, None] = '9d7807cbcb6e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('profiles')]
    if 'response_rate' not in columns:
        op.add_column('profiles', sa.Column('response_rate', sa.Float(), nullable=True, server_default='10.0'))


def downgrade() -> None:
    op.drop_column('profiles', 'response_rate')
