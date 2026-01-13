-- Add new columns to profiles table for business information and phone verification
-- Run this in your PostgreSQL database if the alembic migration fails

-- Add display_name column
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS display_name VARCHAR(255);

-- Add business_name column  
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS business_name VARCHAR(255);

-- Add about column
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS about TEXT;

-- Add phone_verified column
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS phone_verified BOOLEAN DEFAULT FALSE;
