"""Add notification_logs table for tracking sent notifications.

Revision ID: add_notification_logs
Revises: sync_all_models
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'add_notification_logs'
down_revision = 'sync_all_models'


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    
    # 1. Create Table if missing (without raw SQL)
    if 'notification_logs' not in tables:
        op.create_table(
            'notification_logs',
            sa.Column('id', sa.UUID(), primary_key=True),
            sa.Column('user_id', sa.UUID(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('notification_type', sa.String(50), nullable=False),
            sa.Column('status', sa.String(20), nullable=False),
            sa.Column('error_message', sa.Text()),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now())
        )
        # Indexes are automatically created by op.create_table if configured, 
        # or we can add them manually with Alembic functions:
        op.create_index('ix_notification_logs_user_id', 'notification_logs', ['user_id'])
        op.create_index('ix_notification_logs_notification_type', 'notification_logs', ['notification_type'])
        op.create_index('ix_notification_logs_created_at', 'notification_logs', ['created_at'])

def downgrade() -> None:
    pass
