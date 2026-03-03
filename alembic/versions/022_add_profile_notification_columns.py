"""Add notification/privacy/bank columns to profiles

Revision ID: 022_add_profile_notification_columns
Revises: 021_add_wallet_offline_ref
Create Date: 2026-03-03

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '022_add_profile_notification_columns'
down_revision: Union[str, None] = '021_add_wallet_offline_ref'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Notification preferences
    op.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS payment_reminders_enabled BOOLEAN DEFAULT TRUE")
    op.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS rent_reminder_day INTEGER DEFAULT 1")
    op.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS rent_due_day INTEGER DEFAULT 5")
    op.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS rent_reminder_message TEXT")
    op.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS maintenance_reminders_enabled BOOLEAN DEFAULT TRUE")
    op.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS email_notifications BOOLEAN DEFAULT TRUE")
    op.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS sms_notifications BOOLEAN DEFAULT TRUE")
    op.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS push_notifications BOOLEAN DEFAULT FALSE")

    # Privacy settings
    op.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS hide_contact_info BOOLEAN DEFAULT FALSE")

    # Bank details
    op.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS bank_account_number VARCHAR(50)")
    op.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS bank_ifsc_code VARCHAR(20)")
    op.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS bank_name VARCHAR(255)")

    # KYC Documents
    op.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS pan_card_url TEXT")
    op.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS gst_doc_url TEXT")
    op.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS aadhar_front_url TEXT")
    op.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS aadhar_back_url TEXT")
    op.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS dl_front_url TEXT")
    op.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS dl_back_url TEXT")
    op.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS college_company_id_url TEXT")
    op.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS profile_verification_status VARCHAR(20) DEFAULT 'pending'")

    # Hosting experience
    op.execute("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS hosting_since DATE")


def downgrade() -> None:
    op.execute("ALTER TABLE profiles DROP COLUMN IF EXISTS payment_reminders_enabled")
    op.execute("ALTER TABLE profiles DROP COLUMN IF EXISTS rent_reminder_day")
    op.execute("ALTER TABLE profiles DROP COLUMN IF EXISTS rent_due_day")
    op.execute("ALTER TABLE profiles DROP COLUMN IF EXISTS rent_reminder_message")
    op.execute("ALTER TABLE profiles DROP COLUMN IF EXISTS maintenance_reminders_enabled")
    op.execute("ALTER TABLE profiles DROP COLUMN IF EXISTS email_notifications")
    op.execute("ALTER TABLE profiles DROP COLUMN IF EXISTS sms_notifications")
    op.execute("ALTER TABLE profiles DROP COLUMN IF EXISTS push_notifications")
    op.execute("ALTER TABLE profiles DROP COLUMN IF EXISTS hide_contact_info")
    op.execute("ALTER TABLE profiles DROP COLUMN IF EXISTS bank_account_number")
    op.execute("ALTER TABLE profiles DROP COLUMN IF EXISTS bank_ifsc_code")
    op.execute("ALTER TABLE profiles DROP COLUMN IF EXISTS bank_name")
    op.execute("ALTER TABLE profiles DROP COLUMN IF EXISTS pan_card_url")
    op.execute("ALTER TABLE profiles DROP COLUMN IF EXISTS gst_doc_url")
    op.execute("ALTER TABLE profiles DROP COLUMN IF EXISTS aadhar_front_url")
    op.execute("ALTER TABLE profiles DROP COLUMN IF EXISTS aadhar_back_url")
    op.execute("ALTER TABLE profiles DROP COLUMN IF EXISTS dl_front_url")
    op.execute("ALTER TABLE profiles DROP COLUMN IF EXISTS dl_back_url")
    op.execute("ALTER TABLE profiles DROP COLUMN IF EXISTS college_company_id_url")
    op.execute("ALTER TABLE profiles DROP COLUMN IF EXISTS profile_verification_status")
    op.execute("ALTER TABLE profiles DROP COLUMN IF EXISTS hosting_since")
