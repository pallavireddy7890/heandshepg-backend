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
    # Use inspector to safely add columns without raw SQL
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    
    # 1. Update Cities Table
    city_cols = [c['name'] for c in inspector.get_columns('cities')]
    if 'status' not in city_cols:
        op.add_column('cities', sa.Column('status', sa.String(20), server_default='AVAILABLE', nullable=False))
    if 'slug' not in city_cols:
        op.add_column('cities', sa.Column('slug', sa.String(100), nullable=True))
    if 'tagline' not in city_cols:
        op.add_column('cities', sa.Column('tagline', sa.String(200), nullable=True))
    if 'priority_order' not in city_cols:
        op.add_column('cities', sa.Column('priority_order', sa.Integer(), server_default='0', nullable=False))
    
    # 2. Update Areas Table
    area_cols = [c['name'] for c in inspector.get_columns('areas')]
    if 'slug' not in area_cols:
        op.add_column('areas', sa.Column('slug', sa.String(100), nullable=True))
    if 'is_popular' not in area_cols:
        op.add_column('areas', sa.Column('is_popular', sa.Boolean(), server_default='false', nullable=False))
    
    # Static Data Updates
    op.execute("UPDATE cities SET slug = LOWER(REPLACE(name, ' ', '-'))")
    op.execute("UPDATE areas SET slug = LOWER(REPLACE(name, ' ', '-'))")
    op.execute("UPDATE cities SET priority_order = 1 WHERE LOWER(name) IN ('hyderabad', 'hyd')")
    op.execute("UPDATE cities SET priority_order = 2 WHERE LOWER(name) IN ('bangalore', 'bengaluru')")
    op.execute("UPDATE cities SET priority_order = 3 WHERE LOWER(name) = 'chennai'")
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
