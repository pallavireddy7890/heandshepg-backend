"""Add wallet payment_type column

Revision ID: 016_wallet_paytype
Revises: 015_essential_cols
Create Date: 2026-02-06

Adds payment_type column to wallet_transactions table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '016_wallet_paytype'
down_revision: Union[str, None] = '016_add_stay_type'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add payment_type column to wallet_transactions."""
    op.execute("ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS payment_type VARCHAR(20) DEFAULT 'total'")


def downgrade() -> None:
    """Remove payment_type column."""
    op.execute("ALTER TABLE wallet_transactions DROP COLUMN IF EXISTS payment_type")
