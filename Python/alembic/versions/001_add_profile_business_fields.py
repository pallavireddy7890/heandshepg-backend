"""Add profile business fields

Revision ID: add_profile_business_fields
Revises: 
Create Date: 2026-01-13

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_profile_business_fields'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns to profiles table
    op.add_column('profiles', sa.Column('display_name', sa.String(255), nullable=True))
    op.add_column('profiles', sa.Column('business_name', sa.String(255), nullable=True))
    op.add_column('profiles', sa.Column('about', sa.Text(), nullable=True))
    op.add_column('profiles', sa.Column('phone_verified', sa.Boolean(), server_default='false', nullable=True))


def downgrade() -> None:
    op.drop_column('profiles', 'phone_verified')
    op.drop_column('profiles', 'about')
    op.drop_column('profiles', 'business_name')
    op.drop_column('profiles', 'display_name')
