"""Add stay_type, duration_days, and customer_snapshot columns to bookings

Revision ID: 016_add_stay_type
Revises: 015_essential_cols
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision = '016_add_stay_type'
down_revision = '015_essential_cols'


def upgrade() -> None:
    # Use inspector instead of raw SQL
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('bookings')]
    
    # 1. Add missing bookings columns with Inspector check
    if 'stay_type' not in columns:
        op.add_column('bookings', sa.Column('stay_type', sa.String(20), server_default='monthly'))
    if 'duration_days' not in columns:
        op.add_column('bookings', sa.Column('duration_days', sa.Integer()))
    if 'customer_snapshot' not in columns:
        op.add_column('bookings', sa.Column('customer_snapshot', JSONB))


def downgrade() -> None:
    pass
