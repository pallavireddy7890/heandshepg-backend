-- Add security_deposit column to rooms table
ALTER TABLE rooms ADD COLUMN IF NOT EXISTS security_deposit INTEGER;
