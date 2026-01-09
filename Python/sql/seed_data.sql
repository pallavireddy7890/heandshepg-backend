-- He&She PG Seed Data
-- Run: psql -U postgres -d heandshepg_db -f sql/seed_data.sql

-- Insert sample users (password is 'password123' hashed with bcrypt)
INSERT INTO users (id, email, hashed_password, is_active, is_verified) VALUES
    ('a1b2c3d4-e5f6-7890-abcd-ef1234567890', 'admin@heandshepg.com', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.QJVcXU7J9SrX6i', true, true),
    ('b2c3d4e5-f6a7-8901-bcde-f23456789012', 'owner1@example.com', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.QJVcXU7J9SrX6i', true, true),
    ('c3d4e5f6-a7b8-9012-cdef-345678901234', 'owner2@example.com', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.QJVcXU7J9SrX6i', true, true),
    ('d4e5f6a7-b8c9-0123-defa-456789012345', 'customer1@example.com', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.QJVcXU7J9SrX6i', true, true),
    ('e5f6a7b8-c9d0-1234-efab-567890123456', 'customer2@example.com', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.QJVcXU7J9SrX6i', true, true)
ON CONFLICT (id) DO NOTHING;

-- Assign roles
INSERT INTO user_roles (user_id, role) VALUES
    ('a1b2c3d4-e5f6-7890-abcd-ef1234567890', 'admin'),
    ('b2c3d4e5-f6a7-8901-bcde-f23456789012', 'owner'),
    ('c3d4e5f6-a7b8-9012-cdef-345678901234', 'owner'),
    ('d4e5f6a7-b8c9-0123-defa-456789012345', 'customer'),
    ('e5f6a7b8-c9d0-1234-efab-567890123456', 'customer')
ON CONFLICT (user_id, role) DO NOTHING;

-- Create profiles
INSERT INTO profiles (user_id, name, phone, email, city) VALUES
    ('a1b2c3d4-e5f6-7890-abcd-ef1234567890', 'Admin User', '9876543210', 'admin@heandshepg.com', 'Bangalore'),
    ('b2c3d4e5-f6a7-8901-bcde-f23456789012', 'Rajesh Kumar', '9876543211', 'owner1@example.com', 'Bangalore'),
    ('c3d4e5f6-a7b8-9012-cdef-345678901234', 'Priya Sharma', '9876543212', 'owner2@example.com', 'Mumbai'),
    ('d4e5f6a7-b8c9-0123-defa-456789012345', 'Amit Singh', '9876543213', 'customer1@example.com', 'Bangalore'),
    ('e5f6a7b8-c9d0-1234-efab-567890123456', 'Sneha Reddy', '9876543214', 'customer2@example.com', 'Mumbai')
ON CONFLICT (user_id) DO NOTHING;

-- Create owner profiles (KYC)
INSERT INTO owners_profile (user_id, approval_status) VALUES
    ('b2c3d4e5-f6a7-8901-bcde-f23456789012', 'approved'),
    ('c3d4e5f6-a7b8-9012-cdef-345678901234', 'approved')
ON CONFLICT (user_id) DO NOTHING;

-- Create properties
INSERT INTO properties (id, owner_id, title, description, address, city, locality, gender_preference, amenities, monthly_rent, deposit, available_from, status) VALUES
    ('11111111-1111-1111-1111-111111111111', 'b2c3d4e5-f6a7-8901-bcde-f23456789012', 
     'Sunshine PG for Girls', 
     'A comfortable and safe PG accommodation for working women and students. Located in prime area with excellent connectivity.',
     '123, MG Road, Near Metro Station', 'Bangalore', 'Koramangala', 'female',
     ARRAY['WiFi', 'AC', 'Laundry', 'Food', 'Gym', 'CCTV', 'Power Backup'],
     8500, 17000, '2024-01-01', 'active'),
    
    ('22222222-2222-2222-2222-222222222222', 'b2c3d4e5-f6a7-8901-bcde-f23456789012',
     'Green Valley Boys PG',
     'Affordable PG for male students and professionals. Spacious rooms with all modern amenities.',
     '456, Brigade Road', 'Bangalore', 'Indiranagar', 'male',
     ARRAY['WiFi', 'Food', 'Washing Machine', 'Parking', 'Power Backup'],
     7000, 14000, '2024-01-01', 'active'),
    
    ('33333333-3333-3333-3333-333333333333', 'c3d4e5f6-a7b8-9012-cdef-345678901234',
     'Mumbai Dreams Co-Living',
     'Premium co-living space in the heart of Mumbai. Fully furnished with modern interiors.',
     '789, Andheri West', 'Mumbai', 'Andheri', 'mixed',
     ARRAY['WiFi', 'AC', 'Food', 'Gym', 'Swimming Pool', 'House Keeping', 'CCTV'],
     12000, 24000, '2024-01-01', 'active'),
    
    ('44444444-4444-4444-4444-444444444444', 'c3d4e5f6-a7b8-9012-cdef-345678901234',
     'Pearl PG for Ladies',
     'Safe and secure accommodation exclusively for women. Home-like atmosphere with nutritious food.',
     '101, Powai Hills', 'Mumbai', 'Powai', 'female',
     ARRAY['WiFi', 'AC', 'Food', 'Laundry', 'CCTV', '24x7 Security'],
     9500, 19000, '2024-01-01', 'active')
ON CONFLICT (id) DO NOTHING;

-- Create rooms for properties
INSERT INTO rooms (id, property_id, room_type, bed_count, price, is_available) VALUES
    -- Sunshine PG rooms
    ('aaaa1111-1111-1111-1111-111111111111', '11111111-1111-1111-1111-111111111111', 'Single', 1, 8500, true),
    ('aaaa2222-2222-2222-2222-222222222222', '11111111-1111-1111-1111-111111111111', 'Double Sharing', 2, 6500, true),
    ('aaaa3333-3333-3333-3333-333333333333', '11111111-1111-1111-1111-111111111111', 'Triple Sharing', 3, 5500, true),
    
    -- Green Valley rooms
    ('bbbb1111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'Single', 1, 7000, true),
    ('bbbb2222-2222-2222-2222-222222222222', '22222222-2222-2222-2222-222222222222', 'Double Sharing', 2, 5500, false),
    ('bbbb3333-3333-3333-3333-333333333333', '22222222-2222-2222-2222-222222222222', 'Triple Sharing', 3, 4500, true),
    
    -- Mumbai Dreams rooms
    ('cccc1111-1111-1111-1111-111111111111', '33333333-3333-3333-3333-333333333333', 'Single', 1, 12000, true),
    ('cccc2222-2222-2222-2222-222222222222', '33333333-3333-3333-3333-333333333333', 'Double Sharing', 2, 9000, true),
    
    -- Pearl PG rooms
    ('dddd1111-1111-1111-1111-111111111111', '44444444-4444-4444-4444-444444444444', 'Single', 1, 9500, true),
    ('dddd2222-2222-2222-2222-222222222222', '44444444-4444-4444-4444-444444444444', 'Double Sharing', 2, 7500, true)
ON CONFLICT (id) DO NOTHING;

-- Create sample bookings
INSERT INTO bookings (id, property_id, room_id, customer_id, owner_id, start_date, status, amount, security_deposit) VALUES
    ('eeee1111-1111-1111-1111-111111111111', '11111111-1111-1111-1111-111111111111', 'aaaa2222-2222-2222-2222-222222222222',
     'd4e5f6a7-b8c9-0123-defa-456789012345', 'b2c3d4e5-f6a7-8901-bcde-f23456789012',
     '2024-01-15', 'active', 6500, 13000),
    
    ('eeee2222-2222-2222-2222-222222222222', '33333333-3333-3333-3333-333333333333', 'cccc2222-2222-2222-2222-222222222222',
     'e5f6a7b8-c9d0-1234-efab-567890123456', 'c3d4e5f6-a7b8-9012-cdef-345678901234',
     '2024-02-01', 'active', 9000, 18000)
ON CONFLICT (id) DO NOTHING;

-- Create sample reviews
INSERT INTO reviews (property_id, user_id, rating, comment, cleanliness_rating, food_rating, safety_rating) VALUES
    ('11111111-1111-1111-1111-111111111111', 'd4e5f6a7-b8c9-0123-defa-456789012345', 4, 
     'Great place to stay! Clean rooms and friendly staff. Food is homely and delicious.', 5, 4, 5),
    ('22222222-2222-2222-2222-222222222222', 'e5f6a7b8-c9d0-1234-efab-567890123456', 5,
     'Excellent PG with all amenities. Highly recommended for working professionals.', 5, 5, 5),
    ('33333333-3333-3333-3333-333333333333', 'd4e5f6a7-b8c9-0123-defa-456789012345', 4,
     'Modern facilities and great location. Slightly expensive but worth the price.', 4, 4, 5)
ON CONFLICT DO NOTHING;

-- Create sample favorites
INSERT INTO favorites (user_id, property_id) VALUES
    ('d4e5f6a7-b8c9-0123-defa-456789012345', '22222222-2222-2222-2222-222222222222'),
    ('d4e5f6a7-b8c9-0123-defa-456789012345', '44444444-4444-4444-4444-444444444444'),
    ('e5f6a7b8-c9d0-1234-efab-567890123456', '11111111-1111-1111-1111-111111111111')
ON CONFLICT (user_id, property_id) DO NOTHING;

-- Create sample notifications
INSERT INTO notifications (user_id, title, message, type) VALUES
    ('d4e5f6a7-b8c9-0123-defa-456789012345', 'Welcome to He&She PG!', 'Thank you for joining. Start exploring PGs near you.', 'info'),
    ('d4e5f6a7-b8c9-0123-defa-456789012345', 'Booking Confirmed', 'Your booking at Sunshine PG has been confirmed.', 'success'),
    ('b2c3d4e5-f6a7-8901-bcde-f23456789012', 'New Booking Request', 'You have received a new booking request for Sunshine PG.', 'info'),
    ('e5f6a7b8-c9d0-1234-efab-567890123456', 'Payment Reminder', 'Your rent for this month is due in 3 days.', 'warning')
ON CONFLICT DO NOTHING;

-- Create sample invoices
INSERT INTO invoices (tenant_id, booking_id, month, amount, due_date, status) VALUES
    ('d4e5f6a7-b8c9-0123-defa-456789012345', 'eeee1111-1111-1111-1111-111111111111', '2024-02', 6500, '2024-02-05', 'paid'),
    ('d4e5f6a7-b8c9-0123-defa-456789012345', 'eeee1111-1111-1111-1111-111111111111', '2024-03', 6500, '2024-03-05', 'pending'),
    ('e5f6a7b8-c9d0-1234-efab-567890123456', 'eeee2222-2222-2222-2222-222222222222', '2024-02', 9000, '2024-02-05', 'paid'),
    ('e5f6a7b8-c9d0-1234-efab-567890123456', 'eeee2222-2222-2222-2222-222222222222', '2024-03', 9000, '2024-03-05', 'pending')
ON CONFLICT DO NOTHING;

COMMIT;

-- Summary:
-- Created 5 users (1 admin, 2 owners, 2 customers)
-- Created 4 properties (2 in Bangalore, 2 in Mumbai)
-- Created 10 rooms across all properties
-- Created 2 active bookings
-- Created 3 reviews
-- Created 3 favorites
-- Created 4 notifications
-- Created 4 invoices
-- Default password for all users: password123
