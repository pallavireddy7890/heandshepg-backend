"""Add essential missing columns for API fixes

Revision ID: 015_essential_cols
Revises: 014_booking_maint
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '015_essential_cols'
down_revision = '014_booking_maint'


def upgrade() -> None:
    # Use inspector instead of raw SQL
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    # 1. Bookings table - payment tracking columns
    bk_columns = [c['name'] for c in inspector.get_columns('bookings')]
    if 'maintenance_charge' not in bk_columns:
        op.add_column('bookings', sa.Column('maintenance_charge', sa.Integer(), server_default='0'))
    if 'rent_paid' not in bk_columns:
        op.add_column('bookings', sa.Column('rent_paid', sa.Boolean(), server_default='false'))
    if 'deposit_paid' not in bk_columns:
        op.add_column('bookings', sa.Column('deposit_paid', sa.Boolean(), server_default='false'))
    if 'maintenance_paid' not in bk_columns:
        op.add_column('bookings', sa.Column('maintenance_paid', sa.Boolean(), server_default='false'))
    
    # 2. Cities table - additional display columns
    ct_columns = [c['name'] for c in inspector.get_columns('cities')]
    if 'slug' not in ct_columns:
        op.add_column('cities', sa.Column('slug', sa.String(100)))
    if 'tagline' not in ct_columns:
        op.add_column('cities', sa.Column('tagline', sa.String(200)))
    if 'status' not in ct_columns:
        op.add_column('cities', sa.Column('status', sa.String(20), server_default='AVAILABLE'))
    if 'priority_order' not in ct_columns:
        op.add_column('cities', sa.Column('priority_order', sa.Integer(), server_default='0'))
    
    # 3. Create index on cities.slug safely
    indexes = [i['name'] for i in inspector.get_indexes('cities')]
    if 'ix_cities_slug' not in indexes:
        op.create_index('ix_cities_slug', 'cities', ['slug'])


def downgrade() -> None:
    pass
