"""Fix wallet_transactions table schema

Revision ID: 018_fix_wallet_transactions
Revises: 33e133ed828d
Create Date: 2026-03-02

Adds missing columns and enum values to wallet_transactions table.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '018_fix_wallet_transactions'
down_revision: Union[str, None] = '33e133ed828d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Add missing columns
    op.execute("ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS payment_method VARCHAR(20) DEFAULT 'online'")
    op.execute("ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS offline_notes TEXT")
    
    # Add new enum values safely
    # Note: PostgreSQL requires committing the transaction to add enum values in some cases, 
    # but Alembic op.execute handles it within its context.
    op.execute("ALTER TYPE transaction_type ADD VALUE IF NOT EXISTS 'withdrawal'")
    op.execute("ALTER TYPE transaction_status ADD VALUE IF NOT EXISTS 'rejected'")

def downgrade() -> None:
    # Remove added columns
    op.execute("ALTER TABLE wallet_transactions DROP COLUMN IF EXISTS offline_notes")
    op.execute("ALTER TABLE wallet_transactions DROP COLUMN IF EXISTS payment_method")
    
    # Note: Removing enum values is complex in PostgreSQL and generally avoided in downgrades.
    pass
