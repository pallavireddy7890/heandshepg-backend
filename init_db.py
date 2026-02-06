#!/usr/bin/env python3
"""
Production Database Initialization Script
Run this ONCE before first deployment to create all enum types and tables.
Usage: python init_db.py
"""
import os
import sys

# Get DATABASE_URL from environment or use default
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable not set!")
    print("Set it like: export DATABASE_URL=postgresql://user:pass@host:5432/dbname")
    sys.exit(1)

print(f"Connecting to database...")

try:
    import psycopg2
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()
    
    print("Creating enum types...")
    
    # Create all enum types
    enums = [
        ("app_role", ['customer', 'owner', 'admin']),
        ("kyc_status", ['pending', 'approved', 'rejected']),
        ("booking_status", ['requested', 'accepted', 'paid', 'checked_in', 'active', 'completed', 'cancelled', 'vacate_requested', 'vacated']),
        ("payment_type", ['booking', 'monthly_rent', 'refund', 'commission']),
        ("payment_status", ['pending', 'completed', 'failed', 'refunded']),
        ("gender_preference", ['male', 'female', 'mixed']),
        ("invoice_status", ['pending', 'paid', 'overdue', 'cancelled']),
        ("ticket_priority", ['low', 'medium', 'high', 'urgent']),
        ("ticket_status", ['open', 'in_progress', 'resolved', 'closed']),
        ("transaction_type", ['credit', 'debit', 'hold', 'release']),
        ("transaction_status", ['pending', 'otp_sent', 'verified', 'completed', 'failed', 'refunded']),
    ]
    
    for enum_name, values in enums:
        values_str = ", ".join([f"'{v}'" for v in values])
        try:
            cur.execute(f"CREATE TYPE {enum_name} AS ENUM ({values_str});")
            print(f"  ✓ Created enum: {enum_name}")
        except psycopg2.errors.DuplicateObject:
            print(f"  - Enum already exists: {enum_name}")
            conn.rollback()
            conn.autocommit = True
    
    print("\nEnabling uuid-ossp extension...")
    cur.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";")
    print("  ✓ uuid-ossp enabled")
    
    cur.close()
    conn.close()
    
    print("\n✅ Database initialization complete!")
    print("You can now start the application.")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    sys.exit(1)
