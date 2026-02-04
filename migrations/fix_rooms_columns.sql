-- Fix missing columns in rooms table
ALTER TABLE rooms ADD COLUMN IF NOT EXISTS floor_number INTEGER DEFAULT 1;
ALTER TABLE rooms ADD COLUMN IF NOT EXISTS room_number VARCHAR(20);
ALTER TABLE rooms ADD COLUMN IF NOT EXISTS monthly_price INTEGER;
ALTER TABLE rooms ADD COLUMN IF NOT EXISTS daily_price INTEGER;

-- Set default values for existing rows
UPDATE rooms SET floor_number = 1 WHERE floor_number IS NULL;
