"""Add notification/privacy/bank columns to profiles

Revision ID: 022_profile_notify
Revises: 021_add_wallet_offline_ref
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = '022_profile_notify'
down_revision = '021_add_wallet_offline_ref'


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('profiles')]
    
    # 1. Definining column additions
    notifications_bank_cols = [
        ('payment_reminders_enabled', sa.Boolean(), sa.text('TRUE')),
        ('rent_reminder_day', sa.Integer(), sa.text('1')),
        ('rent_due_day', sa.Integer(), sa.text('5')),
        ('rent_reminder_message', sa.Text(), None),
        ('maintenance_reminders_enabled', sa.Boolean(), sa.text('TRUE')),
        ('email_notifications', sa.Boolean(), sa.text('TRUE')),
        ('sms_notifications', sa.Boolean(), sa.text('TRUE')),
        ('push_notifications', sa.Boolean(), sa.text('FALSE')),
        ('hide_contact_info', sa.Boolean(), sa.text('FALSE')),
        ('bank_account_number', sa.String(50), None),
        ('bank_ifsc_code', sa.String(20), None),
        ('bank_name', sa.String(255), None),
        ('pan_card_url', sa.Text(), None),
        ('gst_doc_url', sa.Text(), None),
        ('aadhar_front_url', sa.Text(), None),
        ('aadhar_back_url', sa.Text(), None),
        ('dl_front_url', sa.Text(), None),
        ('dl_back_url', sa.Text(), None),
        ('college_company_id_url', sa.Text(), None),
        ('profile_verification_status', sa.String(20), sa.text("'pending'")),
        ('hosting_since', sa.Date(), None),
    ]
    
    # 2. Safely Apply Each Column
    for col_name, col_type, col_default in notifications_bank_cols:
        if col_name not in columns:
            op.add_column('profiles', sa.Column(col_name, col_type, server_default=col_default))


def downgrade() -> None:
    pass
