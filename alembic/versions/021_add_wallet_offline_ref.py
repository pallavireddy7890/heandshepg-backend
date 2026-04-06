"""Add offline_reference to wallet_transactions

Revision ID: 021_add_wallet_offline_ref
Revises: 020_add_payment_date
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '021_add_wallet_offline_ref'
down_revision = '020_add_payment_date'


def upgrade() -> None:
    # Use inspector instead of raw SQL
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('wallet_transactions')]
    
    # 1. Add offline_reference column safely
    if 'offline_reference' not in columns:
        op.add_column('wallet_transactions', sa.Column('offline_reference', sa.Text()))


def downgrade() -> None:
    pass
