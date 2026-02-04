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
    # Add city_id column to properties table
    op.add_column('properties', sa.Column('city_id', sa.UUID(), nullable=True))
    
    # Add foreign key constraint
    op.create_foreign_key(
        'fk_properties_city_id', 'properties', 'cities', 
        ['city_id'], ['id'], ondelete='SET NULL'
    )
    
    # Create indexes for better performance
    op.create_index(op.f('ix_properties_city'), 'properties', ['city'], unique=False)
    op.create_index(op.f('ix_properties_status'), 'properties', ['status'], unique=False)


def downgrade() -> None:
    # Remove indexes
    op.drop_index(op.f('ix_properties_status'), table_name='properties')
    op.drop_index(op.f('ix_properties_city'), table_name='properties')
    
    # Remove foreign key
    op.drop_constraint('fk_properties_city_id', 'properties', type_='foreignkey')
    
    # Remove column
    op.drop_column('properties', 'city_id')
