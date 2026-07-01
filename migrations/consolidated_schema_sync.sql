-- CONSOLIDATED MIGRATION: All additional schema changes
-- Run this after init_db.py to sync all tables

-- ================================================
-- EMAIL VERIFICATIONS TABLE
-- ================================================
CREATE TABLE IF NOT EXISTS email_verifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL,
    otp_code VARCHAR(6) NOT NULL,
    name VARCHAR(255) NOT NULL,
    phone VARCHAR(20),
    hashed_password VARCHAR(255) NOT NULL,
    role app_role NOT NULL DEFAULT 'customer',
    is_verified BOOLEAN DEFAULT FALSE,
    attempts INTEGER DEFAULT 0,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_email_verifications_email ON email_verifications(email);
CREATE INDEX IF NOT EXISTS idx_email_verifications_expires_at ON email_verifications(expires_at);

-- ================================================
-- ANNOUNCEMENTS TABLE
-- ================================================
CREATE TABLE IF NOT EXISTS announcements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    property_id UUID REFERENCES properties(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    priority VARCHAR(20) DEFAULT 'normal',
    target_audience VARCHAR(20) DEFAULT 'all',
    is_admin BOOLEAN DEFAULT FALSE,
    start_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    end_time TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_announcements_owner ON announcements(owner_id);
CREATE INDEX IF NOT EXISTS idx_announcements_property ON announcements(property_id);

-- ================================================
-- MAINTENANCE TICKETS TABLE
-- ================================================
CREATE TABLE IF NOT EXISTS maintenance_tickets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    property_id UUID REFERENCES properties(id) ON DELETE CASCADE NOT NULL,
    room_id UUID REFERENCES rooms(id) ON DELETE SET NULL,
    booking_id UUID REFERENCES bookings(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    priority ticket_priority DEFAULT 'medium',
    status ticket_status DEFAULT 'open',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_maintenance_tickets_tenant ON maintenance_tickets(tenant_id);
CREATE INDEX IF NOT EXISTS idx_maintenance_tickets_property ON maintenance_tickets(property_id);
CREATE INDEX IF NOT EXISTS idx_maintenance_tickets_status ON maintenance_tickets(status);

-- ================================================
-- CITIES TABLE - Missing columns
-- ================================================
ALTER TABLE cities ADD COLUMN IF NOT EXISTS slug VARCHAR(100);
ALTER TABLE cities ADD COLUMN IF NOT EXISTS tagline VARCHAR(200);
ALTER TABLE cities ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'AVAILABLE';
ALTER TABLE cities ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
ALTER TABLE cities ADD COLUMN IF NOT EXISTS priority_order INTEGER DEFAULT 0;

-- ================================================
-- ROOMS TABLE - Missing columns
-- ================================================
ALTER TABLE rooms ADD COLUMN IF NOT EXISTS floor_number VARCHAR(50) DEFAULT '1';
ALTER TABLE rooms ALTER COLUMN floor_number TYPE VARCHAR(50) USING floor_number::text;
ALTER TABLE rooms ALTER COLUMN floor_number SET DEFAULT '1';
ALTER TABLE rooms ADD COLUMN IF NOT EXISTS room_number VARCHAR(20);
ALTER TABLE rooms ADD COLUMN IF NOT EXISTS monthly_price INTEGER;
ALTER TABLE rooms ADD COLUMN IF NOT EXISTS daily_price INTEGER;
ALTER TABLE rooms ADD COLUMN IF NOT EXISTS area_sqft INTEGER;
ALTER TABLE rooms ADD COLUMN IF NOT EXISTS width_ft INTEGER;
ALTER TABLE rooms ADD COLUMN IF NOT EXISTS has_ventilation BOOLEAN DEFAULT TRUE;
ALTER TABLE rooms ADD COLUMN IF NOT EXISTS room_description TEXT;

-- ================================================
-- BOOKINGS TABLE - Missing columns
-- ================================================
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS bed_id UUID REFERENCES room_beds(id) ON DELETE SET NULL;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS maintenance_charge INTEGER DEFAULT 0;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS rent_paid BOOLEAN DEFAULT FALSE;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS deposit_paid BOOLEAN DEFAULT FALSE;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS maintenance_paid BOOLEAN DEFAULT FALSE;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS stay_type VARCHAR(20) DEFAULT 'monthly';
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS duration_days INTEGER;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS customer_snapshot JSONB;

-- ================================================
-- WALLET TRANSACTIONS TABLE - Missing columns
-- ================================================
ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS payment_type VARCHAR(20) DEFAULT 'total';

-- ================================================
-- PROFILES TABLE - Missing columns
-- ================================================
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS hosting_since DATE;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS owner_available BOOLEAN DEFAULT TRUE;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS available_from VARCHAR(10);
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS available_to VARCHAR(10);
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS available_days TEXT[];

-- ================================================
-- ROOMS TABLE - Additional columns
-- ================================================
ALTER TABLE rooms ADD COLUMN IF NOT EXISTS security_deposit INTEGER;

-- Fix payments metadata column name
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'payments' AND column_name = 'metadata') THEN
        ALTER TABLE payments RENAME COLUMN metadata TO payment_metadata;
    ELSIF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'payments' AND column_name = 'payment_metadata') THEN
        ALTER TABLE payments ADD COLUMN payment_metadata JSONB;
    END IF;
END $$;
