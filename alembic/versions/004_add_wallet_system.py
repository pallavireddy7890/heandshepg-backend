"""Add wallet system tables.

Revision ID: 004
Revises: 003_add_notification_logs
Create Date: 2026-01-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '004_add_wallet_system'
down_revision = 'add_notification_logs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    
    # 1. Create Enum Types with idempotency
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'transaction_type') THEN
                CREATE TYPE transaction_type AS ENUM ('credit', 'debit', 'hold', 'release');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'transaction_status') THEN
                CREATE TYPE transaction_status AS ENUM ('pending', 'otp_sent', 'verified', 'completed', 'failed', 'refunded');
            END IF;
        END $$;
    """)
    
    # 2. Create Wallets Table if missing
    if 'wallets' not in tables:
        op.create_table(
            'wallets',
            sa.Column('id', sa.UUID(), primary_key=True),
            sa.Column('user_id', sa.UUID(), sa.ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False),
            sa.Column('balance', sa.Integer(), server_default='0'),
            sa.Column('pending_balance', sa.Integer(), server_default='0'),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now())
        )
    
    # 3. Create Wallet Transactions Table if missing
    if 'wallet_transactions' not in tables:
        op.create_table(
            'wallet_transactions',
            sa.Column('id', sa.UUID(), primary_key=True),
            sa.Column('wallet_id', sa.UUID(), sa.ForeignKey('wallets.id', ondelete='CASCADE'), nullable=False),
            sa.Column('amount', sa.Integer(), nullable=False),
            sa.Column('transaction_type', sa.Enum('credit', 'debit', 'hold', 'release', name='transaction_type', create_type=False), nullable=False),
            sa.Column('status', sa.Enum('pending', 'otp_sent', 'verified', 'completed', 'failed', 'refunded', name='transaction_status', create_type=False), server_default='pending'),
            sa.Column('reference_id', sa.String(length=255)),
            sa.Column('metadata', sa.JSON()),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now())
        )
    
    # 4. Create Transaction OTPs Table if missing
    if 'transaction_otps' not in tables:
        op.create_table(
            'transaction_otps',
            sa.Column('id', sa.UUID(), primary_key=True),
            sa.Column('transaction_id', sa.UUID(), sa.ForeignKey('wallet_transactions.id', ondelete='CASCADE'), nullable=False),
            sa.Column('otp_code', sa.String(6), nullable=False),
            sa.Column('otp_type', sa.String(20), nullable=False),
            sa.Column('user_id', sa.UUID(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('is_verified', sa.Boolean(), server_default='false'),
            sa.Column('attempts', sa.Integer(), server_default='0'),
            sa.Column('max_attempts', sa.Integer(), server_default='3'),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('verified_at', sa.DateTime(timezone=True)),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now())
        )

def downgrade() -> None:
    pass
