"""Standalone script to repair production database schema.
Adds missing columns and enum values that might have been skipped during migrations.
"""
import sys
import os
from sqlalchemy import text
from sqlalchemy.orm import Session

# Add the project directory to sys.path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal, engine
from app.config import get_settings

settings = get_settings()

def repair_db():
    print(f"Connecting to database: {settings.database_url.split('@')[-1]}")
    db = SessionLocal()
    
    try:
        # --- MIGRATION 018: Wallet Transactions ---
        print("Checking Wallet Transactions (018)...")
        db.execute(text("ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS payment_method VARCHAR(20) DEFAULT 'online'"))
        db.execute(text("ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS offline_notes TEXT"))
        
        # Enums (PostgreSQL specific)
        try:
            db.execute(text("ALTER TYPE transaction_type ADD VALUE IF NOT EXISTS 'withdrawal'"))
            db.execute(text("ALTER TYPE transaction_status ADD VALUE IF NOT EXISTS 'rejected'"))
            db.commit()
        except Exception as e:
            print(f"Note on enums (018): {e}")
            db.rollback()

        # --- MIGRATION 019: Payments ---
        print("Checking Payments (019)...")
        db.execute(text("ALTER TABLE payments ADD COLUMN IF NOT EXISTS payment_method VARCHAR(20) DEFAULT 'online'"))
        db.execute(text("ALTER TABLE payments ADD COLUMN IF NOT EXISTS offline_reference TEXT"))
        db.execute(text("ALTER TABLE payments ADD COLUMN IF NOT EXISTS verified_by_id UUID"))
        
        # Foreign Key for payments.verified_by_id
        db.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints 
                    WHERE constraint_name='fk_payments_verified_by_id' AND table_name='payments'
                ) THEN
                    ALTER TABLE payments ADD CONSTRAINT fk_payments_verified_by_id 
                    FOREIGN KEY (verified_by_id) REFERENCES users(id) ON DELETE SET NULL;
                END IF;
            END $$;
        """))
        
        try:
            db.execute(text("ALTER TYPE payment_status ADD VALUE IF NOT EXISTS 'pending_verification'"))
            db.commit()
        except Exception as e:
            print(f"Note on enums (019): {e}")
            db.rollback()

        # --- MIGRATION 020: Payment Date ---
        print("Checking Payment Date (020)...")
        db.execute(text("ALTER TABLE payments ADD COLUMN IF NOT EXISTS payment_date TIMESTAMP WITH TIME ZONE"))

        # --- MIGRATION 021: Wallet Offline Ref ---
        print("Checking Wallet Offline Ref (021)...")
        db.execute(text("ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS offline_reference TEXT"))

        # --- MIGRATION 022: Profiles (Notification/Privacy/Bank/KYC) ---
        print("Checking Profiles (022)...")
        profile_cols = [
            ("payment_reminders_enabled", "BOOLEAN DEFAULT TRUE"),
            ("rent_reminder_day", "INTEGER DEFAULT 1"),
            ("rent_due_day", "INTEGER DEFAULT 5"),
            ("rent_reminder_message", "TEXT"),
            ("maintenance_reminders_enabled", "BOOLEAN DEFAULT TRUE"),
            ("email_notifications", "BOOLEAN DEFAULT TRUE"),
            ("sms_notifications", "BOOLEAN DEFAULT TRUE"),
            ("push_notifications", "BOOLEAN DEFAULT FALSE"),
            ("hide_contact_info", "BOOLEAN DEFAULT FALSE"),
            ("bank_account_number", "VARCHAR(50)"),
            ("bank_ifsc_code", "VARCHAR(20)"),
            ("bank_name", "VARCHAR(255)"),
            ("pan_card_url", "TEXT"),
            ("gst_doc_url", "TEXT"),
            ("aadhar_front_url", "TEXT"),
            ("aadhar_back_url", "TEXT"),
            ("dl_front_url", "TEXT"),
            ("dl_back_url", "TEXT"),
            ("college_company_id_url", "TEXT"),
            ("profile_verification_status", "VARCHAR(20) DEFAULT 'pending'"),
            ("hosting_since", "DATE")
        ]
        
        for col, col_type in profile_cols:
            db.execute(text(f"ALTER TABLE profiles ADD COLUMN IF NOT EXISTS {col} {col_type}"))

        # --- MIGRATION 023: Email Verifications Referral Code ---
        print("Checking Email Verifications (023)...")
        db.execute(text("ALTER TABLE email_verifications ADD COLUMN IF NOT EXISTS referral_code VARCHAR(20)"))

        db.commit()
        print("SUCCESS: Database schema repair completed.")
        
    except Exception as e:
        db.rollback()
        print(f"ERROR: Failed to repair database: {e}")
        # Re-raise to ensure script failure is visible
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    repair_db()
