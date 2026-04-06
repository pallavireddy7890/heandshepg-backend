"""Sync all model changes with database

Revision ID: sync_all_models
Revises: add_profile_business_fields
Create Date: 2026-01-18
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'sync_all_models'
down_revision: Union[str, None] = 'add_profile_business_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use inspector to safely add columns/tables without raw SQL
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()
    
    # 1. Update Profiles Table
    profile_cols = [c['name'] for c in inspector.get_columns('profiles')]
    profile_adds = [
        ('current_address', sa.Text()),
        ('permanent_address', sa.Text()),
        ('gender', sa.String(20)),
        ('date_of_birth', sa.String(20)),
        ('email_notifications', sa.Boolean(), sa.ColumnDefault(True)),
        ('sms_notifications', sa.Boolean(), sa.ColumnDefault(True)),
        ('push_notifications', sa.Boolean(), sa.ColumnDefault(False)),
        ('hide_contact_info', sa.Boolean(), sa.ColumnDefault(False)),
        ('bank_account_number', sa.String(50)),
        ('bank_ifsc_code', sa.String(20)),
        ('bank_name', sa.String(255)),
        ('pan_card_url', sa.Text()),
        ('gst_doc_url', sa.Text()),
        ('aadhar_front_url', sa.Text()),
        ('aadhar_back_url', sa.Text()),
        ('college_company_id_url', sa.Text()),
        ('profile_verification_status', sa.String(20), sa.ColumnDefault('pending')),
    ]
    for col_name, col_type, *defaults in profile_adds:
        if col_name not in profile_cols:
            op.add_column('profiles', sa.Column(col_name, col_type, *defaults))
    
    # 2. Create Tables if missing
    if 'referral_codes' not in tables:
        op.create_table(
            'referral_codes',
            sa.Column('id', sa.UUID(), primary_key=True),
            sa.Column('user_id', sa.UUID(), sa.ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False),
            sa.Column('code', sa.String(20), unique=True, nullable=False),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now())
        )
    
    if 'roommate_profiles' not in tables:
        op.create_table(
            'roommate_profiles',
            sa.Column('id', sa.UUID(), primary_key=True),
            sa.Column('user_id', sa.UUID(), sa.ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False),
            sa.Column('gender', sa.String(20)),
            sa.Column('budget_min', sa.Integer()),
            sa.Column('budget_max', sa.Integer()),
            sa.Column('move_in_date', sa.DateTime(timezone=True)),
            sa.Column('bio', sa.Text()),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now())
        )
    
    # 3. Update Referrals Table
    if 'referrals' in tables:
        ref_cols = [c['name'] for c in inspector.get_columns('referrals')]
        ref_adds = [
            ('referred_id', sa.UUID()),
            ('referral_code_id', sa.UUID()),
            ('status', sa.String(20), sa.ColumnDefault('pending')),
            ('booking_id', sa.UUID()),
            ('completed_at', sa.DateTime(timezone=True)),
        ]
        for col_name, col_type, *defaults in ref_adds:
            if col_name not in ref_cols:
                op.add_column('referrals', sa.Column(col_name, col_type, *defaults))


def downgrade() -> None:
    pass
