"""add referral_code to email_verifications

Revision ID: 023_add_referral_code_to_email_verifications
Revises: 022_add_profile_notification_columns
Create Date: 2026-03-18

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '023_add_referral_code_to_email_verifications'
down_revision: Union[str, None] = '022_add_profile_notification_columns'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE email_verifications ADD COLUMN IF NOT EXISTS referral_code VARCHAR(20)")


def downgrade() -> None:
    op.execute("ALTER TABLE email_verifications DROP COLUMN IF EXISTS referral_code")
