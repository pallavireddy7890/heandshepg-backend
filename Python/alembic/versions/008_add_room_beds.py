"""Add room_beds table

Revision ID: 008
Revises: 007_add_room_description
Create Date: 2026-02-02

This migration creates the room_beds table which is required for the RoomBed model
that tracks individual beds within rooms.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '008_add_room_beds'
down_revision: Union[str, None] = '007_add_room_description'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create room_beds table."""
    op.execute("""
        CREATE TABLE IF NOT EXISTS room_beds (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            room_id UUID REFERENCES rooms(id) ON DELETE CASCADE NOT NULL,
            bed_number VARCHAR(20),
            status VARCHAR(20) DEFAULT 'available',
            current_tenant_id UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)


def downgrade() -> None:
    """Drop room_beds table."""
    op.execute("DROP TABLE IF EXISTS room_beds CASCADE")
