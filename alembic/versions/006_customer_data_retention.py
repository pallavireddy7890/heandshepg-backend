"""Add customer data retention for bookings

Revision ID: 006_customer_data_retention
Revises: 005_city_management
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision = '006_customer_data_retention'
down_revision = '005_city_management'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('bookings')]
    
    # 1. Add customer_snapshot column if missing
    if 'customer_snapshot' not in columns:
        op.add_column('bookings', sa.Column('customer_snapshot', JSONB, nullable=True))
    
    # 2. Safely Update Foreign Key
    # Note: we use inspect to see if it's already nullable
    for col in inspector.get_columns('bookings'):
        if col['name'] == 'customer_id' and col['nullable'] is False:
            op.alter_column('bookings', 'customer_id', existing_type=sa.UUID(), nullable=True)

    # 3. Handle Constraints with raw SQL IF NOT EXISTS (since Alembic has no inspector for FKEY names easily)
    # Actually, we can use try/except for constraint drops if they are already done
    try:
        op.drop_constraint('bookings_customer_id_fkey', 'bookings', type_='foreignkey')
    except Exception:
        pass
        
    op.create_foreign_key(
        'bookings_customer_id_fkey',
        'bookings', 'users',
        ['customer_id'], ['id'],
        ondelete='SET NULL'
    )
    
    # Static Data Updates
    op.execute("UPDATE bookings SET customer_snapshot = '{}' WHERE customer_snapshot IS NULL")


def downgrade() -> None:
    pass
