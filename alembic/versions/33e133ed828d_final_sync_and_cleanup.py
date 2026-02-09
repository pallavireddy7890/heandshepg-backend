"""final_sync_and_cleanup

Revision ID: 33e133ed828d
Revises: 017_sync_all
Create Date: 2026-02-07 14:47:32.003266

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '33e133ed828d'
down_revision: Union[str, None] = '017_sync_all'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # === EMAIL VERIFICATIONS TABLE ===
    op.execute("""
        CREATE TABLE IF NOT EXISTS email_verifications (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email VARCHAR(255) NOT NULL,
            phone VARCHAR(20),
            otp_code VARCHAR(6) NOT NULL,
            name VARCHAR(255) NOT NULL,
            hashed_password VARCHAR(255) NOT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'customer',
            is_verified BOOLEAN DEFAULT FALSE,
            attempts INTEGER DEFAULT 0,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_email_verifications_email ON email_verifications(email)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_email_verifications_expires_at ON email_verifications(expires_at)")

    # === PROFILES TABLE ===
    profile_columns = [
        "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS hosting_since DATE",
        "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS owner_available BOOLEAN DEFAULT TRUE",
        "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS available_from VARCHAR(10)",
        "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS available_to VARCHAR(10)",
        "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS available_days TEXT[]"
    ]
    for sql in profile_columns:
        op.execute(sql)

    # === ROOMS TABLE ===
    room_columns = [
        "ALTER TABLE rooms ADD COLUMN IF NOT EXISTS caption TEXT",
        "ALTER TABLE rooms ADD COLUMN IF NOT EXISTS area_sqft INTEGER",
        "ALTER TABLE rooms ADD COLUMN IF NOT EXISTS width_ft INTEGER",
        "ALTER TABLE rooms ADD COLUMN IF NOT EXISTS has_ventilation BOOLEAN DEFAULT TRUE",
        "ALTER TABLE rooms ADD COLUMN IF NOT EXISTS security_deposit INTEGER",
        "ALTER TABLE rooms ADD COLUMN IF NOT EXISTS floor_number INTEGER DEFAULT 1",
        "ALTER TABLE rooms ADD COLUMN IF NOT EXISTS room_number VARCHAR(20)",
        "ALTER TABLE rooms ADD COLUMN IF NOT EXISTS monthly_price INTEGER",
        "ALTER TABLE rooms ADD COLUMN IF NOT EXISTS daily_price INTEGER"
    ]
    for sql in room_columns:
        op.execute(sql)

    # === BOOKING STATUS ENUM ===
    # Adding enum values safely
    op.execute("ALTER TYPE booking_status ADD VALUE IF NOT EXISTS 'vacate_requested'")
    op.execute("ALTER TYPE booking_status ADD VALUE IF NOT EXISTS 'vacated'")


def downgrade() -> None:
    # Minimal downgrade - remove columns added
    op.execute("ALTER TABLE profiles DROP COLUMN IF EXISTS available_days")
    op.execute("ALTER TABLE profiles DROP COLUMN IF EXISTS available_to")
    op.execute("ALTER TABLE profiles DROP COLUMN IF EXISTS available_from")
    op.execute("ALTER TABLE profiles DROP COLUMN IF EXISTS owner_available")
    op.execute("ALTER TABLE profiles DROP COLUMN IF EXISTS hosting_since")

    op.execute("ALTER TABLE rooms DROP COLUMN IF EXISTS daily_price")
    op.execute("ALTER TABLE rooms DROP COLUMN IF EXISTS monthly_price")
    op.execute("ALTER TABLE rooms DROP COLUMN IF EXISTS room_number")
    op.execute("ALTER TABLE rooms DROP COLUMN IF EXISTS floor_number")
    op.execute("ALTER TABLE rooms DROP COLUMN IF EXISTS security_deposit")
    op.execute("ALTER TABLE rooms DROP COLUMN IF EXISTS has_ventilation")
    op.execute("ALTER TABLE rooms DROP COLUMN IF EXISTS width_ft")
    op.execute("ALTER TABLE rooms DROP COLUMN IF EXISTS area_sqft")
    op.execute("ALTER TABLE rooms DROP COLUMN IF EXISTS caption")

    op.execute("DROP TABLE IF EXISTS email_verifications")
