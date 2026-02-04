"""Add notification_logs table for tracking sent notifications.

Revision ID: add_notification_logs
Revises: sync_all_models
Create Date: 2026-01-18

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_notification_logs'
down_revision = 'sync_all_models'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create notification_logs table."""
    op.execute("""
        CREATE TABLE IF NOT EXISTS notification_logs (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
            notification_type VARCHAR(50) NOT NULL,
            status VARCHAR(20) NOT NULL,
            error_message TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)
    # Create indexes
    op.execute("CREATE INDEX IF NOT EXISTS ix_notification_logs_user_id ON notification_logs(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_notification_logs_notification_type ON notification_logs(notification_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_notification_logs_created_at ON notification_logs(created_at)")


def downgrade() -> None:
    """Drop notification_logs table."""
    op.execute("DROP TABLE IF EXISTS notification_logs CASCADE")
