"""Sync all schema - comprehensive migration

Revision ID: 017_sync_all
Revises: 016_wallet_paytype
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision = '017_sync_all'
down_revision = '016_wallet_paytype'

def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    
    # 1. Update Areas Table
    if 'areas' in tables:
        area_cols = [c['name'] for c in inspector.get_columns('areas')]
        if 'slug' not in area_cols:
            op.add_column('areas', sa.Column('slug', sa.String(100)))
        if 'is_popular' not in area_cols:
            op.add_column('areas', sa.Column('is_popular', sa.Boolean(), server_default='false'))
        
        area_idx = [i['name'] for i in inspector.get_indexes('areas')]
        if 'ix_areas_slug' not in area_idx:
            op.create_index('ix_areas_slug', 'areas', ['slug'])

    # 2. Update Payments Table
    if 'payments' in tables:
        pay_cols = [c['name'] for c in inspector.get_columns('payments')]
        if 'metadata' in pay_cols and 'payment_metadata' not in pay_cols:
            op.alter_column('payments', 'metadata', new_column_name='payment_metadata')
        elif 'payment_metadata' not in pay_cols:
            op.add_column('payments', sa.Column('payment_metadata', JSONB))

    # 3. Update Bookings Table
    if 'bookings' in tables:
        bk_cols = [c['name'] for c in inspector.get_columns('bookings')]
        # Make customer_id nullable safely
        for col in inspector.get_columns('bookings'):
            if col['name'] == 'customer_id' and col['nullable'] is False:
                op.alter_column('bookings', 'customer_id', existing_type=sa.UUID(), nullable=True)
        
        # Check and fix constraints
        bk_constraints = [c['name'] for c in inspector.get_foreign_keys('bookings')]
        if 'bookings_customer_id_fkey' in bk_constraints:
            op.drop_constraint('bookings_customer_id_fkey', 'bookings', type_='foreignkey')
            op.create_foreign_key(
                'bookings_customer_id_fkey',
                'bookings', 'users',
                ['customer_id'], ['id'],
                ondelete='SET NULL'
            )
        
        # Add indexes safely
        bk_idx = [i['name'] for i in inspector.get_indexes('bookings')]
        idx_to_add = [
            ('ix_bookings_customer_id', ['customer_id']),
            ('ix_bookings_owner_id', ['owner_id']),
            ('ix_bookings_status', ['status']),
        ]
        for idx_name, cols in idx_to_add:
            if idx_name not in bk_idx:
                op.create_index(idx_name, 'bookings', cols)

    # 4. Clean up Cities
    if 'cities' in tables:
        city_cols = [c['name'] for c in inspector.get_columns('cities')]
        if 'display_order' in city_cols:
            op.drop_column('cities', 'display_order')

    # 5. Handle generic indexes if tables exist
    table_indexes = [
        ('favorites', 'ix_favorites_user_id', ['user_id']),
        ('messages', 'ix_messages_from_user', ['from_user']),
        ('messages', 'ix_messages_to_user', ['to_user']),
        ('notification_logs', 'ix_notification_logs_created_at', ['created_at']),
        ('notification_logs', 'ix_notification_logs_notification_type', ['notification_type']),
        ('notification_logs', 'ix_notification_logs_user_id', ['user_id']),
        ('notifications', 'ix_notifications_user_id', ['user_id']),
        ('properties', 'ix_properties_city', ['city']),
        ('properties', 'ix_properties_status', ['status']),
        ('reviews', 'ix_reviews_property_id', ['property_id']),
        ('users', 'ix_users_email', ['email']),
    ]
    for tbl, idx_name, cols in table_indexes:
        if tbl in tables:
            idx_list = [i['name'] for i in inspector.get_indexes(tbl)]
            if idx_name not in idx_list:
                # Special case for unique email index
                is_unique = (idx_name == 'ix_users_email')
                op.create_index(idx_name, tbl, cols, unique=is_unique)

def downgrade() -> None:
    pass
