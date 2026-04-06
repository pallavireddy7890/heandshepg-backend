"""add referral_code to email_verifications

Revision ID: 023_add_referral_code_to_email_verifications
Revises: 022_add_profile_notification_columns
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '023_add_referral_code_to_email_verifications'
down_revision = '022_add_profile_notification_columns'


def upgrade() -> None:
    # Use inspector instead of raw SQL
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    # Check if table exists first (in case it was dropped by a later migration)
    if 'email_verifications' in inspector.get_table_names():
        columns = [c['name'] for c in inspector.get_columns('email_verifications')]
        if 'referral_code' not in columns:
            op.add_column('email_verifications', sa.Column('referral_code', sa.String(20), nullable=True))


def downgrade() -> None:
    pass
