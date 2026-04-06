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
    
    # 2. Create Wallets Table
    op.execute("""
        CREATE TABLE IF NOT EXISTS wallets (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            balance INTEGER DEFAULT 0,
            pending_balance INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS ix_wallets_user_id ON wallets(user_id);
    """)

    # 3. Create Wallet Transactions Table
    op.execute("""
        CREATE TABLE IF NOT EXISTS wallet_transactions (
            id UUID PRIMARY KEY,
            wallet_id UUID NOT NULL REFERENCES wallets(id) ON DELETE CASCADE,
            booking_id UUID REFERENCES bookings(id) ON DELETE SET NULL,
            payer_id UUID REFERENCES users(id) ON DELETE SET NULL,
            receiver_id UUID REFERENCES users(id) ON DELETE SET NULL,
            amount INTEGER NOT NULL,
            transaction_type transaction_type NOT NULL,
            status transaction_status DEFAULT 'pending',
            otp_verified BOOLEAN DEFAULT FALSE,
            otp_verified_at TIMESTAMP WITH TIME ZONE,
            razorpay_payment_id VARCHAR(255),
            razorpay_order_id VARCHAR(255),
            description TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS ix_wallet_transactions_wallet_id ON wallet_transactions(wallet_id);
        CREATE INDEX IF NOT EXISTS ix_wallet_transactions_status ON wallet_transactions(status);
    """)
    
    # 4. Create Transaction OTPs Table
    op.execute("""
        CREATE TABLE IF NOT EXISTS transaction_otps (
            id UUID PRIMARY KEY,
            transaction_id UUID NOT NULL REFERENCES wallet_transactions(id) ON DELETE CASCADE,
            otp_code VARCHAR(6) NOT NULL,
            otp_type VARCHAR(20) NOT NULL,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            is_verified BOOLEAN DEFAULT FALSE,
            attempts INTEGER DEFAULT 0,
            max_attempts INTEGER DEFAULT 3,
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
            verified_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS ix_transaction_otps_transaction_id ON transaction_otps(transaction_id);
    """)

def downgrade() -> None:
    op.drop_table('transaction_otps')
    op.drop_table('wallet_transactions')
    op.drop_table('wallets')
    op.execute("DROP TYPE IF EXISTS transaction_status")
    op.execute("DROP TYPE IF EXISTS transaction_type")
