-- Add owner availability columns to profiles table
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS owner_available BOOLEAN DEFAULT TRUE;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS available_from VARCHAR(10);
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS available_to VARCHAR(10);
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS available_days TEXT[];
