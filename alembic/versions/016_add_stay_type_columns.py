"""Add stay_type, duration_days, and customer_snapshot columns to bookings

Revision ID: 016_add_stay_type
Revises: 015_essential_cols
Create Date: 2026-02-06

Adds the missing columns that are in the Booking model but not in the database:
- stay_type: VARCHAR(20) DEFAULT 'monthly'
- duration_days: INTEGER
- customer_snapshot: JSONB
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = '016_add_stay_type'
down_revision: Union[str, None] = '015_essential_cols'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add stay_type, duration_days, and customer_snapshot columns to bookings."""
    
    # Add missing bookings columns
    booking_columns = [
        "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS stay_type VARCHAR(20) DEFAULT 'monthly'",
        "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS duration_days INTEGER",
        "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS customer_snapshot JSONB",
    ]
    
    for sql in booking_columns:
        op.execute(sql)


def downgrade() -> None:
    """Remove stay_type, duration_days, and customer_snapshot columns from bookings."""
    op.execute("ALTER TABLE bookings DROP COLUMN IF EXISTS customer_snapshot")
    op.execute("ALTER TABLE bookings DROP COLUMN IF EXISTS duration_days")
    op.execute("ALTER TABLE bookings DROP COLUMN IF EXISTS stay_type")
