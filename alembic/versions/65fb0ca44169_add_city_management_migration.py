"""add_city_management_migration

Revision ID: 65fb0ca44169
Revises: 012_room_floors_beds
Create Date: 2026-02-03 15:55:21.472061
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '65fb0ca44169'
down_revision: Union[str, None] = '012_room_floors_beds'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use inspector instead of raw SQL
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('properties')]
    
    # 1. Add city_id column to properties table if missing
    if 'city_id' not in columns:
        op.add_column('properties', sa.Column('city_id', sa.UUID(), nullable=True))
    
    # 2. Add foreign key constraint safely
    # Note: Alembic's create_foreign_key doesn't have IF NOT EXISTS, 
    # but we can try/except or check existing constraints.
    try:
        op.create_foreign_key(
            'fk_properties_city_id', 'properties', 'cities', 
            ['city_id'], ['id'], ondelete='SET NULL'
        )
    except Exception:
        pass # Already exists
    
    # 3. Create indexes safely
    # Get existing indexes
    indexes = [i['name'] for i in inspector.get_indexes('properties')]
    
    if 'ix_properties_city' not in indexes:
        op.create_index(op.f('ix_properties_city'), 'properties', ['city'], unique=False)
    if 'ix_properties_status' not in indexes:
        op.create_index(op.f('ix_properties_status'), 'properties', ['status'], unique=False)


def downgrade() -> None:
    pass
