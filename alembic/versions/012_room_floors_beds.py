"""Add room floor, room_number, and pricing fields

Revision ID: 012_room_floors_beds
Revises: 009_payment_columns
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '012_room_floors_beds'
down_revision = '009_payment_columns'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('rooms')]
    
    # 1. Add missing columns with Inspector check
    if 'floor_number' not in columns:
        op.add_column('rooms', sa.Column('floor_number', sa.Integer(), server_default='1'))
    if 'room_number' not in columns:
        op.add_column('rooms', sa.Column('room_number', sa.String(20)))
    if 'monthly_price' not in columns:
        op.add_column('rooms', sa.Column('monthly_price', sa.Integer()))
    if 'daily_price' not in columns:
        op.add_column('rooms', sa.Column('daily_price', sa.Integer()))


def downgrade() -> None:
    pass
