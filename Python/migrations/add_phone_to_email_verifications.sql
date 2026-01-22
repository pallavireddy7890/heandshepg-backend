-- Migration: Add phone column to email_verifications table
-- Run this script to add the phone column for mandatory phone signup

ALTER TABLE email_verifications ADD COLUMN IF NOT EXISTS phone VARCHAR(20);

-- Comment on column
COMMENT ON COLUMN email_verifications.phone IS 'User phone number collected during signup';
