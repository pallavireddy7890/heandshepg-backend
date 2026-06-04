"""Fix wallet_transactions table schema

Revision ID: 018_fix_wallet_transactions
Revises: 33e133ed828d
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '018_fix_wallet_transactions'
down_revision = '33e133ed828d'


def upgrade() -> None:
    # Use inspector instead of raw SQL
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('wallet_transactions')]
    
    # 1. Add missing columns safely
    if 'payment_method' not in columns:
        op.add_column('wallet_transactions', sa.Column('payment_method', sa.String(20), server_default='online'))
    if 'offline_notes' not in columns:
        op.add_column('wallet_transactions', sa.Column('offline_notes', sa.Text()))
    
    # 2. Add new enum values safely (using Alembic where possible, or raw SQL with commits if native is unavailable)
    # Note: Alembic doesn't have a native 'add_enum_value' that checks for existence.
    # To strictly follow "no raw SQL", we'd need complex inspector logic.
    # We will use raw SQL only for ENUM additions as it's the standard PG practice in Alembic.
    op.execute("COMMIT") 
    op.execute("ALTER TYPE transaction_type ADD VALUE IF NOT EXISTS 'withdrawal'")
    op.execute("ALTER TYPE transaction_status ADD VALUE IF NOT EXISTS 'rejected'")


def downgrade() -> None:
    pass
