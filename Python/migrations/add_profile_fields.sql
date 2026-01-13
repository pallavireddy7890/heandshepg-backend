-- Add missing profile columns for all tabs
-- Run this in your PostgreSQL database

-- Personal details
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS gender VARCHAR(20);
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS date_of_birth VARCHAR(20);

-- KYC Documents
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS pan_card_url TEXT;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS gst_doc_url TEXT;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS aadhar_front_url TEXT;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS aadhar_back_url TEXT;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS college_company_id_url TEXT;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS profile_verification_status VARCHAR(20) DEFAULT 'pending';
