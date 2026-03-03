"""Add offline_reference to wallet_transactions

Revision ID: 021_add_wallet_offline_ref
Revises: 020_add_payment_date
Create Date: 2026-03-03

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '021_add_wallet_offline_ref'
down_revision: Union[str, None] = '020_add_payment_date'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS offline_reference TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE wallet_transactions DROP COLUMN IF EXISTS offline_reference")
