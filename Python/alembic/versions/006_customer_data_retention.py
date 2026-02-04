"""Add customer data retention for bookings

Revision ID: 006_customer_data_retention
Revises: 005_city_management
Create Date: 2026-02-02

Changes:
- Change customer_id foreign key from CASCADE to SET NULL
- Make customer_id nullable
- Add customer_snapshot JSONB column to store customer info
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers
revision = '006_customer_data_retention'
down_revision = '005_city_management'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add customer_snapshot column
    op.add_column('bookings', sa.Column('customer_snapshot', JSONB, nullable=True))
    
    # Drop the existing foreign key constraint
    op.drop_constraint('bookings_customer_id_fkey', 'bookings', type_='foreignkey')
    
    # Make customer_id nullable
    op.alter_column('bookings', 'customer_id',
                    existing_type=UUID(as_uuid=True),
                    nullable=True)
    
    # Recreate foreign key with SET NULL behavior
    op.create_foreign_key(
        'bookings_customer_id_fkey',
        'bookings', 'users',
        ['customer_id'], ['id'],
        ondelete='SET NULL'
    )
    
    # Backfill customer_snapshot for existing bookings
    op.execute("""
        UPDATE bookings b
        SET customer_snapshot = jsonb_build_object(
            'name', COALESCE(p.name, u.email),
            'email', u.email,
            'phone', p.phone
        )
        FROM users u
        LEFT JOIN profiles p ON p.user_id = u.id
        WHERE b.customer_id = u.id
        AND b.customer_snapshot IS NULL
    """)


def downgrade() -> None:
    # Note: Downgrade will fail if there are bookings with null customer_id
    # because we're changing back to NOT NULL
    
    # Drop the SET NULL foreign key
    op.drop_constraint('bookings_customer_id_fkey', 'bookings', type_='foreignkey')
    
    # Make customer_id NOT NULL again (will fail if nulls exist)
    op.alter_column('bookings', 'customer_id',
                    existing_type=UUID(as_uuid=True),
                    nullable=False)
    
    # Recreate foreign key with CASCADE
    op.create_foreign_key(
        'bookings_customer_id_fkey',
        'bookings', 'users',
        ['customer_id'], ['id'],
        ondelete='CASCADE'
    )
    
    # Remove customer_snapshot column
    op.drop_column('bookings', 'customer_snapshot')
