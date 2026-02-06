"""Sync all schema - comprehensive migration

Revision ID: 017_sync_all
Revises: 016_wallet_paytype
Create Date: 2026-02-06

Comprehensive schema sync using safe SQL with IF NOT EXISTS patterns.
This migration adds missing columns and safely handles schema differences.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '017_sync_all'
down_revision: Union[str, None] = '016_wallet_paytype'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Sync all schema differences safely."""
    
    # === AREAS TABLE ===
    area_columns = [
        "ALTER TABLE areas ADD COLUMN IF NOT EXISTS slug VARCHAR(100)",
        "ALTER TABLE areas ADD COLUMN IF NOT EXISTS is_popular BOOLEAN DEFAULT FALSE",
    ]
    for sql in area_columns:
        op.execute(sql)
    
    # Create index safely
    op.execute("CREATE INDEX IF NOT EXISTS ix_areas_slug ON areas(slug)")
    
    # === PAYMENTS TABLE ===
    # Rename metadata to payment_metadata if metadata exists and payment_metadata doesn't
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='payments' AND column_name='metadata')
               AND NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='payments' AND column_name='payment_metadata') THEN
                ALTER TABLE payments RENAME COLUMN metadata TO payment_metadata;
            ELSIF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='payments' AND column_name='payment_metadata') THEN
                ALTER TABLE payments ADD COLUMN payment_metadata JSONB;
            END IF;
        END $$;
    """)
    
    # === BOOKINGS TABLE ===
    # Make customer_id nullable if it isn't already
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.columns 
                       WHERE table_name='bookings' AND column_name='customer_id' AND is_nullable='NO') THEN
                ALTER TABLE bookings ALTER COLUMN customer_id DROP NOT NULL;
            END IF;
        END $$;
    """)
    
    # Update foreign key constraint safely
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.table_constraints 
                       WHERE constraint_name='bookings_customer_id_fkey' AND table_name='bookings') THEN
                ALTER TABLE bookings DROP CONSTRAINT bookings_customer_id_fkey;
                ALTER TABLE bookings ADD CONSTRAINT bookings_customer_id_fkey 
                    FOREIGN KEY (customer_id) REFERENCES users(id) ON DELETE SET NULL;
            END IF;
        END $$;
    """)
    
    # Add indexes to bookings safely
    op.execute("CREATE INDEX IF NOT EXISTS ix_bookings_customer_id ON bookings(customer_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_bookings_owner_id ON bookings(owner_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_bookings_status ON bookings(status)")
    
    # === CITIES TABLE ===
    # Drop old display_order column if exists (replaced by priority_order)
    op.execute("ALTER TABLE cities DROP COLUMN IF EXISTS display_order")
    
    # === FAVORITES TABLE ===
    op.execute("CREATE INDEX IF NOT EXISTS ix_favorites_user_id ON favorites(user_id)")
    
    # === MESSAGES TABLE ===
    op.execute("CREATE INDEX IF NOT EXISTS ix_messages_from_user ON messages(from_user)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_messages_to_user ON messages(to_user)")
    
    # === NOTIFICATION LOGS TABLE ===
    op.execute("CREATE INDEX IF NOT EXISTS ix_notification_logs_created_at ON notification_logs(created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_notification_logs_notification_type ON notification_logs(notification_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_notification_logs_user_id ON notification_logs(user_id)")
    
    # === NOTIFICATIONS TABLE ===
    op.execute("CREATE INDEX IF NOT EXISTS ix_notifications_user_id ON notifications(user_id)")
    
    # === PROPERTIES TABLE ===
    op.execute("CREATE INDEX IF NOT EXISTS ix_properties_city ON properties(city)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_properties_status ON properties(status)")
    
    # === REVIEWS TABLE ===
    op.execute("CREATE INDEX IF NOT EXISTS ix_reviews_property_id ON reviews(property_id)")
    
    # === USERS TABLE ===
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users(email)")


def downgrade() -> None:
    """Reverse schema sync - minimal implementation."""
    # Generally we don't want to downgrade in production
    # Just drop the indexes we added
    op.execute("DROP INDEX IF EXISTS ix_areas_slug")
    op.execute("DROP INDEX IF EXISTS ix_bookings_customer_id")
    op.execute("DROP INDEX IF EXISTS ix_bookings_owner_id")
    op.execute("DROP INDEX IF EXISTS ix_bookings_status")
    op.execute("DROP INDEX IF EXISTS ix_favorites_user_id")
    op.execute("DROP INDEX IF EXISTS ix_messages_from_user")
    op.execute("DROP INDEX IF EXISTS ix_messages_to_user")
    op.execute("DROP INDEX IF EXISTS ix_notification_logs_created_at")
    op.execute("DROP INDEX IF EXISTS ix_notification_logs_notification_type")
    op.execute("DROP INDEX IF EXISTS ix_notification_logs_user_id")
    op.execute("DROP INDEX IF EXISTS ix_notifications_user_id")
    op.execute("DROP INDEX IF EXISTS ix_properties_city")
    op.execute("DROP INDEX IF EXISTS ix_properties_status")
    op.execute("DROP INDEX IF EXISTS ix_reviews_property_id")
    op.execute("DROP INDEX IF EXISTS ix_users_email")
    
    # Remove added columns
    op.execute("ALTER TABLE areas DROP COLUMN IF EXISTS slug")
    op.execute("ALTER TABLE areas DROP COLUMN IF EXISTS is_popular")
