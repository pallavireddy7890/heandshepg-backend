"""Sync all model changes with database

Revision ID: sync_all_models
Revises: add_profile_business_fields
Create Date: 2026-01-18

This migration ensures all model columns and tables exist in the database.
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
    # Add missing profile columns
    profile_columns = [
        ('current_address', sa.Text()),
        ('permanent_address', sa.Text()),
        ('gender', sa.String(20)),
        ('date_of_birth', sa.String(20)),
        ('email_notifications', sa.Boolean(), 'true'),
        ('sms_notifications', sa.Boolean(), 'true'),
        ('push_notifications', sa.Boolean(), 'false'),
        ('hide_contact_info', sa.Boolean(), 'false'),
        ('bank_account_number', sa.String(50)),
        ('bank_ifsc_code', sa.String(20)),
        ('bank_name', sa.String(255)),
        ('pan_card_url', sa.Text()),
        ('gst_doc_url', sa.Text()),
        ('aadhar_front_url', sa.Text()),
        ('aadhar_back_url', sa.Text()),
        ('college_company_id_url', sa.Text()),
        ('profile_verification_status', sa.String(20), 'pending'),
    ]
    
    for col_def in profile_columns:
        col_name = col_def[0]
        col_type = col_def[1]
        default = col_def[2] if len(col_def) > 2 else None
        try:
            if default:
                op.add_column('profiles', sa.Column(col_name, col_type, server_default=default, nullable=True))
            else:
                op.add_column('profiles', sa.Column(col_name, col_type, nullable=True))
        except Exception:
            pass  # Column may already exist
    
    # Create referral_codes table
    op.execute("""
        CREATE TABLE IF NOT EXISTS referral_codes (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID REFERENCES users(id) ON DELETE CASCADE UNIQUE NOT NULL,
            code VARCHAR(20) UNIQUE NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)
    
    # Create roommate_profiles table
    op.execute("""
        CREATE TABLE IF NOT EXISTS roommate_profiles (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID REFERENCES users(id) ON DELETE CASCADE UNIQUE NOT NULL,
            age INTEGER,
            gender VARCHAR(20),
            occupation VARCHAR(100),
            budget_min INTEGER,
            budget_max INTEGER,
            preferred_location VARCHAR(255),
            preferred_city VARCHAR(100),
            move_in_date TIMESTAMP WITH TIME ZONE,
            preferences TEXT[],
            languages TEXT[],
            hobbies TEXT[],
            bio TEXT,
            dietary_preference VARCHAR(50),
            smoking BOOLEAN DEFAULT FALSE,
            drinking BOOLEAN DEFAULT FALSE,
            pets_allowed BOOLEAN DEFAULT FALSE,
            cleanliness_level INTEGER DEFAULT 3,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)
    
    # Create roommate_matches table
    op.execute("""
        CREATE TABLE IF NOT EXISTS roommate_matches (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
            matched_user_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
            match_score DECIMAL(5,2),
            status VARCHAR(20) DEFAULT 'pending',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)
    
    # Create cities table
    op.execute("""
        CREATE TABLE IF NOT EXISTS cities (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            name VARCHAR(100) UNIQUE NOT NULL,
            image_url TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            display_order VARCHAR(10) DEFAULT '0',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)
    
    # Create areas table
    op.execute("""
        CREATE TABLE IF NOT EXISTS areas (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            city_id UUID REFERENCES cities(id) ON DELETE CASCADE NOT NULL,
            name VARCHAR(100) NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            display_order VARCHAR(10) DEFAULT '0',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)
    
    # Update referrals table to match new schema (add missing columns)
    try:
        op.add_column('referrals', sa.Column('referred_id', sa.UUID(), nullable=True))
        op.add_column('referrals', sa.Column('referral_code_id', sa.UUID(), nullable=True))
        op.add_column('referrals', sa.Column('status', sa.String(20), server_default='pending'))
        op.add_column('referrals', sa.Column('booking_id', sa.UUID(), nullable=True))
        op.add_column('referrals', sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True))
    except Exception:
        pass  # Columns may already exist


def downgrade() -> None:
    # Drop new tables
    op.execute("DROP TABLE IF EXISTS areas CASCADE")
    op.execute("DROP TABLE IF EXISTS cities CASCADE")
    op.execute("DROP TABLE IF EXISTS roommate_matches CASCADE")
    op.execute("DROP TABLE IF EXISTS roommate_profiles CASCADE")
    op.execute("DROP TABLE IF EXISTS referral_codes CASCADE")
    
    # Drop new profile columns
    profile_columns = [
        'current_address', 'permanent_address', 'gender', 'date_of_birth',
        'email_notifications', 'sms_notifications', 'push_notifications',
        'hide_contact_info', 'bank_account_number', 'bank_ifsc_code', 'bank_name',
        'pan_card_url', 'gst_doc_url', 'aadhar_front_url', 'aadhar_back_url',
        'college_company_id_url', 'profile_verification_status'
    ]
    for col in profile_columns:
        try:
            op.drop_column('profiles', col)
        except Exception:
            pass
