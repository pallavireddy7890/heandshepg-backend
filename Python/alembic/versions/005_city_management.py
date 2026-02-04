"""Add city management fields.

Revision ID: 005
Revises: 004_add_wallet_system
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '005_city_management'
down_revision = '004_add_wallet_system'
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns to cities table
    op.add_column('cities', sa.Column('status', sa.String(20), server_default='AVAILABLE', nullable=False))
    op.add_column('cities', sa.Column('slug', sa.String(100), nullable=True))
    op.add_column('cities', sa.Column('tagline', sa.String(200), nullable=True))
    op.add_column('cities', sa.Column('priority_order', sa.Integer(), server_default='0', nullable=False))
    
    # Add new columns to areas table
    op.add_column('areas', sa.Column('slug', sa.String(100), nullable=True))
    op.add_column('areas', sa.Column('is_popular', sa.Boolean(), server_default='false', nullable=False))
    
    # Update existing cities to have slug (lowercase name)
    op.execute("UPDATE cities SET slug = LOWER(REPLACE(name, ' ', '-'))")
    op.execute("UPDATE areas SET slug = LOWER(REPLACE(name, ' ', '-'))")
    
    # Set Hyderabad and Bangalore as priority 1 and 2
    op.execute("UPDATE cities SET priority_order = 1 WHERE LOWER(name) IN ('hyderabad', 'hyd')")
    op.execute("UPDATE cities SET priority_order = 2 WHERE LOWER(name) IN ('bangalore', 'bengaluru')")
    op.execute("UPDATE cities SET priority_order = 3 WHERE LOWER(name) = 'chennai'")
    
    # Add taglines
    op.execute("UPDATE cities SET tagline = 'City of Pearls' WHERE LOWER(name) IN ('hyderabad', 'hyd')")
    op.execute("UPDATE cities SET tagline = 'Silicon Valley of India' WHERE LOWER(name) IN ('bangalore', 'bengaluru')")
    op.execute("UPDATE cities SET tagline = 'Gateway to South India' WHERE LOWER(name) = 'chennai'")


def downgrade():
    op.drop_column('cities', 'status')
    op.drop_column('cities', 'slug')
    op.drop_column('cities', 'tagline')
    op.drop_column('cities', 'priority_order')
    op.drop_column('areas', 'slug')
    op.drop_column('areas', 'is_popular')
