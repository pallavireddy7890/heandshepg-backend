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
    # Add missing profile columns using raw SQL with IF NOT EXISTS
    profile_columns_sql = [
        "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS current_address TEXT",
        "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS permanent_address TEXT",
        "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS gender VARCHAR(20)",
        "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS date_of_birth VARCHAR(20)",
        "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS email_notifications BOOLEAN DEFAULT TRUE",
        "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS sms_notifications BOOLEAN DEFAULT TRUE",
        "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS push_notifications BOOLEAN DEFAULT FALSE",
        "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS hide_contact_info BOOLEAN DEFAULT FALSE",
        "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS bank_account_number VARCHAR(50)",
        "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS bank_ifsc_code VARCHAR(20)",
        "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS bank_name VARCHAR(255)",
        "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS pan_card_url TEXT",
        "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS gst_doc_url TEXT",
        "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS aadhar_front_url TEXT",
        "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS aadhar_back_url TEXT",
        "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS college_company_id_url TEXT",
        "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS profile_verification_status VARCHAR(20) DEFAULT 'pending'",
    ]
    
    for sql in profile_columns_sql:
        op.execute(sql)
    
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
    referral_columns_sql = [
        "ALTER TABLE referrals ADD COLUMN IF NOT EXISTS referred_id UUID",
        "ALTER TABLE referrals ADD COLUMN IF NOT EXISTS referral_code_id UUID",
        "ALTER TABLE referrals ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'pending'",
        "ALTER TABLE referrals ADD COLUMN IF NOT EXISTS booking_id UUID",
        "ALTER TABLE referrals ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP WITH TIME ZONE",
    ]
    for sql in referral_columns_sql:
        op.execute(sql)


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
