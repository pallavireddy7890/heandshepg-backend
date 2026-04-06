"""Add booking maintenance and payment tracking columns

Revision ID: 014_add_booking_maintenance_columns
Revises: 013_add_booking_bed_id
Create Date: 2026-02-06

This migration adds the maintenance_charge, rent_paid, deposit_paid, 
and maintenance_paid columns to the bookings table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '014_booking_maint'
down_revision: Union[str, None] = '013_add_booking_bed_id'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use inspector instead of raw SQL
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('bookings')]
    
    # 1. Add maintenance_charge column if missing
    if 'maintenance_charge' not in columns:
        op.add_column('bookings', sa.Column('maintenance_charge', sa.Integer(), nullable=True, server_default='0'))
    
    # 2. Add payment tracking boolean columns if missing
    if 'rent_paid' not in columns:
        op.add_column('bookings', sa.Column('rent_paid', sa.Boolean(), nullable=True, server_default='false'))
    if 'deposit_paid' not in columns:
        op.add_column('bookings', sa.Column('deposit_paid', sa.Boolean(), nullable=True, server_default='false'))
    if 'maintenance_paid' not in columns:
        op.add_column('bookings', sa.Column('maintenance_paid', sa.Boolean(), nullable=True, server_default='false'))


def downgrade() -> None:
    """Remove maintenance and payment tracking columns from bookings table."""
    op.drop_column('bookings', 'maintenance_paid')
    op.drop_column('bookings', 'deposit_paid')
    op.drop_column('bookings', 'rent_paid')
    op.drop_column('bookings', 'maintenance_charge')
