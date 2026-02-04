"""Add room floor, room_number, and pricing fields

Revision ID: 012_room_floors_beds
Revises: 011
Create Date: 2026-02-02
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '012_room_floors_beds'
down_revision = '009_payment_columns'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add floor_number to rooms
    op.add_column('rooms', sa.Column('floor_number', sa.Integer(), nullable=True, server_default='1'))
    
    # Add room_number to rooms
    op.add_column('rooms', sa.Column('room_number', sa.String(20), nullable=True))
    
    # Add separate monthly and daily pricing
    op.add_column('rooms', sa.Column('monthly_price', sa.Integer(), nullable=True))
    op.add_column('rooms', sa.Column('daily_price', sa.Integer(), nullable=True))
    
    # Migrate existing price to monthly_price
    op.execute("UPDATE rooms SET monthly_price = price WHERE monthly_price IS NULL")
    op.execute("UPDATE rooms SET floor_number = 1 WHERE floor_number IS NULL")


def downgrade() -> None:
    op.drop_column('rooms', 'daily_price')
    op.drop_column('rooms', 'monthly_price')
    op.drop_column('rooms', 'room_number')
    op.drop_column('rooms', 'floor_number')
