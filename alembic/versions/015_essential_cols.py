"""Add essential missing columns for API fixes

Revision ID: 015_essential_cols
Revises: 014_booking_maint
Create Date: 2026-02-06

Adds only the essential missing columns to fix current API errors:
- bookings: maintenance_charge, rent_paid, deposit_paid, maintenance_paid
- cities: slug, tagline, status, priority_order
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '015_essential_cols'
down_revision: Union[str, None] = '014_booking_maint'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add essential missing columns using ADD COLUMN IF NOT EXISTS for safety."""
    
    # Bookings table - payment tracking columns
    booking_columns = [
        "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS maintenance_charge INTEGER DEFAULT 0",
        "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS rent_paid BOOLEAN DEFAULT FALSE",
        "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS deposit_paid BOOLEAN DEFAULT FALSE",
        "ALTER TABLE bookings ADD COLUMN IF NOT EXISTS maintenance_paid BOOLEAN DEFAULT FALSE",
    ]
    
    for sql in booking_columns:
        op.execute(sql)
    
    # Cities table - additional display columns
    city_columns = [
        "ALTER TABLE cities ADD COLUMN IF NOT EXISTS slug VARCHAR(100)",
        "ALTER TABLE cities ADD COLUMN IF NOT EXISTS tagline VARCHAR(200)",
        "ALTER TABLE cities ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'AVAILABLE'",
        "ALTER TABLE cities ADD COLUMN IF NOT EXISTS priority_order INTEGER DEFAULT 0",
    ]
    
    for sql in city_columns:
        op.execute(sql)
    
    # Create index on cities.slug if not exists
    op.execute("CREATE INDEX IF NOT EXISTS ix_cities_slug ON cities(slug)")


def downgrade() -> None:
    """Remove added columns."""
    # Cities
    op.execute("DROP INDEX IF EXISTS ix_cities_slug")
    op.execute("ALTER TABLE cities DROP COLUMN IF EXISTS priority_order")
    op.execute("ALTER TABLE cities DROP COLUMN IF EXISTS status")
    op.execute("ALTER TABLE cities DROP COLUMN IF EXISTS tagline")
    op.execute("ALTER TABLE cities DROP COLUMN IF EXISTS slug")
    
    # Bookings
    op.execute("ALTER TABLE bookings DROP COLUMN IF EXISTS maintenance_paid")
    op.execute("ALTER TABLE bookings DROP COLUMN IF EXISTS deposit_paid")
    op.execute("ALTER TABLE bookings DROP COLUMN IF EXISTS rent_paid")
    op.execute("ALTER TABLE bookings DROP COLUMN IF EXISTS maintenance_charge")
