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
    # Add new columns to profiles table using IF NOT EXISTS
    op.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS display_name VARCHAR(255)")
    op.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS business_name VARCHAR(255)")
    op.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS about TEXT")
    op.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS phone_verified BOOLEAN DEFAULT FALSE")


def downgrade() -> None:
    op.drop_column('profiles', 'phone_verified')
    op.drop_column('profiles', 'about')
    op.drop_column('profiles', 'business_name')
    op.drop_column('profiles', 'display_name')

