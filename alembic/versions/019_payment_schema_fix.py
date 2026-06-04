"""Fix payment schema - add missing columns and enum values

Revision ID: 019_payment_schema_fix
Revises: 018_fix_wallet_transactions
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision = '019_payment_schema_fix'
down_revision = '018_fix_wallet_transactions'


def upgrade() -> None:
    # Use inspector instead of raw SQL
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('payments')]
    
    # 1. Add missing columns safely
    if 'payment_method' not in columns:
        op.add_column('payments', sa.Column('payment_method', sa.String(20), server_default='online'))
    if 'offline_reference' not in columns:
        op.add_column('payments', sa.Column('offline_reference', sa.Text()))
    if 'verified_by_id' not in columns:
        op.add_column('payments', sa.Column('verified_by_id', sa.UUID()))
    
    # 2. Add foreign key safely
    constraints = [c['name'] for c in inspector.get_foreign_keys('payments')]
    if 'fk_payments_verified_by_id' not in constraints:
        op.create_foreign_key(
            'fk_payments_verified_by_id',
            'payments', 'users',
            ['verified_by_id'], ['id'],
            ondelete='SET NULL'
        )

    # 3. Add new value to payment_status enum
    # Native check is complex for enums, using safe raw SQL
    op.execute("COMMIT")
    op.execute("ALTER TYPE payment_status ADD VALUE IF NOT EXISTS 'pending_verification'")


def downgrade() -> None:
    pass
