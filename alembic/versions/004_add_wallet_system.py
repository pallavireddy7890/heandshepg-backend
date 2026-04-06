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
    # Create enum types
    transaction_type_enum = postgresql.ENUM(
        'credit', 'debit', 'hold', 'release',
        name='transaction_type',
        create_type=False
    )
    transaction_status_enum = postgresql.ENUM(
        'pending', 'otp_sent', 'verified', 'completed', 'failed', 'refunded',
        name='transaction_status',
        create_type=False
    )
    
    # Create enums
    # Create transaction_type/status enums with idempotency
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE transaction_type AS ENUM ('credit', 'debit', 'hold', 'release');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE transaction_status AS ENUM ('pending', 'otp_sent', 'verified', 'completed', 'failed', 'refunded');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    
    # Create wallets table
    op.create_table(
        'wallets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False),
        sa.Column('balance', sa.Integer(), default=0),
        sa.Column('pending_balance', sa.Integer(), default=0),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('ix_wallets_user_id', 'wallets', ['user_id'])
    
    # Create wallet_transactions table
    op.create_table(
        'wallet_transactions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('wallet_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('wallets.id', ondelete='CASCADE'), nullable=False),
        sa.Column('booking_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('bookings.id', ondelete='SET NULL')),
        sa.Column('payer_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('receiver_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('transaction_type', postgresql.ENUM('credit', 'debit', 'hold', 'release', name='transaction_type', create_type=False), nullable=False),
        sa.Column('status', postgresql.ENUM('pending', 'otp_sent', 'verified', 'completed', 'failed', 'refunded', name='transaction_status', create_type=False), default='pending'),
        sa.Column('otp_verified', sa.Boolean(), default=False),
        sa.Column('otp_verified_at', sa.DateTime(timezone=True)),
        sa.Column('razorpay_payment_id', sa.String(255)),
        sa.Column('razorpay_order_id', sa.String(255)),
        sa.Column('description', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('ix_wallet_transactions_wallet_id', 'wallet_transactions', ['wallet_id'])
    op.create_index('ix_wallet_transactions_booking_id', 'wallet_transactions', ['booking_id'])
    op.create_index('ix_wallet_transactions_status', 'wallet_transactions', ['status'])
    
    # Create transaction_otps table
    op.create_table(
        'transaction_otps',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('transaction_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('wallet_transactions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('otp_code', sa.String(6), nullable=False),
        sa.Column('otp_type', sa.String(20), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('is_verified', sa.Boolean(), default=False),
        sa.Column('attempts', sa.Integer(), default=0),
        sa.Column('max_attempts', sa.Integer(), default=3),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('verified_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_transaction_otps_transaction_id', 'transaction_otps', ['transaction_id'])


def downgrade() -> None:
    op.drop_table('transaction_otps')
    op.drop_table('wallet_transactions')
    op.drop_table('wallets')
    op.execute("DROP TYPE IF EXISTS transaction_status")
    op.execute("DROP TYPE IF EXISTS transaction_type")
