"""Add payment_date column to payments table

Revision ID: 020_add_payment_date
Revises: 019_payment_schema_fix
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '020_add_payment_date'
down_revision = '019_payment_schema_fix'


def upgrade() -> None:
    # Use inspector instead of raw SQL
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('payments')]
    
    # 1. Add payment_date column safely
    if 'payment_date' not in columns:
        op.add_column('payments', sa.Column('payment_date', sa.DateTime(timezone=True)))


def downgrade() -> None:
    pass
