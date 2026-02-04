"""Add missing columns to payments table

Revision ID: 009_payment_columns
Revises: 008_add_room_beds
Create Date: 2026-02-02

This migration adds missing columns to the payments table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = '009_payment_columns'
down_revision: Union[str, None] = '008_add_room_beds'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add missing columns to payments table."""
    # Add commission_amount if not exists
    op.execute("ALTER TABLE payments ADD COLUMN IF NOT EXISTS commission_amount INTEGER DEFAULT 0")
    # Add payment_metadata if not exists
    op.execute("ALTER TABLE payments ADD COLUMN IF NOT EXISTS payment_metadata JSONB")


def downgrade() -> None:
    """Remove added columns."""
    op.execute("ALTER TABLE payments DROP COLUMN IF EXISTS commission_amount")
    op.execute("ALTER TABLE payments DROP COLUMN IF EXISTS payment_metadata")
