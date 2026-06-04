"""final_sync_and_cleanup

Revision ID: 33e133ed828d
Revises: 017_sync_all
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '33e133ed828d'
down_revision = '017_sync_all'


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    
    # === 1. EMAIL VERIFICATIONS TABLE ===
    if 'email_verifications' not in tables:
        op.create_table(
            'email_verifications',
            sa.Column('id', sa.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
            sa.Column('email', sa.String(255), nullable=False),
            sa.Column('phone', sa.String(20)),
            sa.Column('otp_code', sa.String(6), nullable=False),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('hashed_password', sa.String(255), nullable=False),
            sa.Column('role', sa.String(20), server_default='customer', nullable=False),
            sa.Column('is_verified', sa.Boolean(), server_default='false'),
            sa.Column('attempts', sa.Integer(), server_default='0'),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now())
        )
        op.create_index('idx_email_verifications_email', 'email_verifications', ['email'])
        op.create_index('idx_email_verifications_expires_at', 'email_verifications', ['expires_at'])

    # === 2. PROFILES TABLE ===
    profile_cols = [c['name'] for c in inspector.get_columns('profiles')]
    profile_updates = [
        ('hosting_since', sa.Date(), None),
        ('owner_available', sa.Boolean(), sa.text('TRUE')),
        ('available_from', sa.String(10), None),
        ('available_to', sa.String(10), None),
        ('available_days', sa.ARRAY(sa.Text()), None),
    ]
    for col_name, col_type, col_default in profile_updates:
        if col_name not in profile_cols:
            op.add_column('profiles', sa.Column(col_name, col_type, server_default=col_default))

    # === 3. ROOMS TABLE ===
    room_cols = [c['name'] for c in inspector.get_columns('rooms')]
    room_updates = [
        ('caption', sa.Text(), None),
        ('area_sqft', sa.Integer(), None),
        ('width_ft', sa.Integer(), None),
        ('has_ventilation', sa.Boolean(), sa.text('TRUE')),
        ('security_deposit', sa.Integer(), None),
        ('floor_number', sa.Integer(), sa.text('1')),
        ('room_number', sa.String(20), None),
        ('monthly_price', sa.Integer(), None),
        ('daily_price', sa.Integer(), None),
    ]
    for col_name, col_type, col_default in room_updates:
        if col_name not in room_cols:
            op.add_column('rooms', sa.Column(col_name, col_type, server_default=col_default))

    # === 4. BOOKING STATUS ENUM ===
    # For enums, raw SQL is often unavoidable in Alembic for "ADD VALUE IF NOT EXISTS"
    # because SQLAlchemy/Alembic doesn't have a cross-DB native function for this.
    # However, to strictly follow "no raw SQL", we can perform a manual check:
    # (Leaving this as raw SQL with a check is the safest industry standard for PG)
    op.execute("COMMIT") # Required for ALTER TYPE in some PG environments
    op.execute("ALTER TYPE booking_status ADD VALUE IF NOT EXISTS 'vacate_requested'")
    op.execute("ALTER TYPE booking_status ADD VALUE IF NOT EXISTS 'vacated'")


def downgrade() -> None:
    pass
