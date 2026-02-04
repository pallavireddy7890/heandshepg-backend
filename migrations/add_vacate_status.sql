-- Migration to add vacate_requested and vacated statuses to booking_status enum
-- Run this migration to fix the vacate functionality

-- Add new enum values to booking_status
ALTER TYPE booking_status ADD VALUE IF NOT EXISTS 'vacate_requested';
ALTER TYPE booking_status ADD VALUE IF NOT EXISTS 'vacated';

-- Note: PostgreSQL doesn't support transactional DDL for ALTER TYPE
-- These changes take effect immediately
