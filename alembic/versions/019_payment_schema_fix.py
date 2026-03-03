"""Fix payment schema - add missing columns and enum values

Revision ID: 019_payment_schema_fix
Revises: 018_fix_wallet_transactions
Create Date: 2026-03-03

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '019_payment_schema_fix'
down_revision: Union[str, None] = '018_fix_wallet_transactions'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add missing columns to payments table safely
    op.execute("ALTER TABLE payments ADD COLUMN IF NOT EXISTS payment_method VARCHAR(20) DEFAULT 'online'")
    op.execute("ALTER TABLE payments ADD COLUMN IF NOT EXISTS offline_reference TEXT")
    op.execute("ALTER TABLE payments ADD COLUMN IF NOT EXISTS verified_by_id UUID")
    
    # Add foreign key safely (if verified_by_id was just added)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints 
                WHERE constraint_name='fk_payments_verified_by_id' AND table_name='payments'
            ) THEN
                ALTER TABLE payments ADD CONSTRAINT fk_payments_verified_by_id 
                FOREIGN KEY (verified_by_id) REFERENCES users(id) ON DELETE SET NULL;
            END IF;
        END $$;
    """)

    # Add new value to payment_status enum
    op.execute("ALTER TYPE payment_status ADD VALUE IF NOT EXISTS 'pending_verification'")


def downgrade() -> None:
    # Remove added columns
    op.execute("ALTER TABLE payments DROP COLUMN IF EXISTS verified_by_id")
    op.execute("ALTER TABLE payments DROP COLUMN IF EXISTS offline_reference")
    op.execute("ALTER TABLE payments DROP COLUMN IF EXISTS payment_method")
    
    # Note: Removing enum values is complex in PostgreSQL and generally avoided.
    pass
