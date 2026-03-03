"""Add payment_date column to payments table

Revision ID: 020_add_payment_date
Revises: 019_payment_schema_fix
Create Date: 2026-03-03

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '020_add_payment_date'
down_revision: Union[str, None] = '019_payment_schema_fix'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add payment_date column safely
    op.execute("ALTER TABLE payments ADD COLUMN IF NOT EXISTS payment_date TIMESTAMP WITH TIME ZONE")


def downgrade() -> None:
    # Remove added column
    op.execute("ALTER TABLE payments DROP COLUMN IF EXISTS payment_date")
