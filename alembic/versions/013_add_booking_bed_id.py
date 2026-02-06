"""Add bed_id column to bookings table

Revision ID: 013_add_booking_bed_id
Revises: 012_room_floors_beds
Create Date: 2026-02-06

This migration adds the bed_id column to the bookings table to track
which specific bed a booking is for.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '013_add_booking_bed_id'
down_revision: Union[str, None] = '65fb0ca44169'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add bed_id column to bookings table."""
    op.add_column('bookings', sa.Column('bed_id', UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_bookings_bed_id_room_beds',
        'bookings', 'room_beds',
        ['bed_id'], ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    """Remove bed_id column from bookings table."""
    op.drop_constraint('fk_bookings_bed_id_room_beds', 'bookings', type_='foreignkey')
    op.drop_column('bookings', 'bed_id')
