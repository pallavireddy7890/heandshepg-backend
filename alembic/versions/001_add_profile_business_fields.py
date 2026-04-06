"""Add profile business fields

Revision ID: add_profile_business_fields
Revises: 
Create Date: 2026-01-13
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = 'add_profile_business_fields'
down_revision = None


def upgrade() -> None:
    # Use inspector instead of raw SQL
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('profiles')]
    
    # Add new columns to profiles table safely
    if 'display_name' not in columns:
        op.add_column('profiles', sa.Column('display_name', sa.String(255)))
    if 'business_name' not in columns:
        op.add_column('profiles', sa.Column('business_name', sa.String(255)))
    if 'about' not in columns:
        op.add_column('profiles', sa.Column('about', sa.Text()))
    if 'phone_verified' not in columns:
        op.add_column('profiles', sa.Column('phone_verified', sa.Boolean(), server_default='false'))


def downgrade() -> None:
    pass
