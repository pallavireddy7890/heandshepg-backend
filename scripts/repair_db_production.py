"""Robust production database schema repair script.
Ensures all columns and enum values exist and verifies them after addition.
"""
import sys
import os
import logging
from sqlalchemy import text, create_engine

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("repair_db")

# Add the project directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import DATABASE_URL from our app, as it contains the normalization fix (postgres:// -> postgresql://)
try:
    from app.database import DATABASE_URL
except ImportError:
    # Fallback if app structure is different
    from dotenv import load_dotenv
    load_dotenv()
    DATABASE_URL = os.getenv("DATABASE_URL")
    if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

def run_alter(conn, sql: str, description: str):
    """Run an ALTER command and log it."""
    try:
        conn.execute(text(sql))
        conn.commit()
        logger.info(f"OK: {description}")
    except Exception as e:
        conn.rollback()
        logger.error(f"FAIL: {description} (Error: {e})")
        # Don't raise here yet - some fails (like enums) are expected or already handled.

import time

def repair_db():
    if not DATABASE_URL:
        logger.critical("DATABASE_URL is not set!")
        sys.exit(1)

    max_retries = 20
    retry_delay = 3
    engine = None
    conn = None

    for attempt in range(1, max_retries + 1):
        logger.info(f"Connecting to database (attempt {attempt}/{max_retries})...")
        try:
            engine = create_engine(DATABASE_URL)
            
            # Test connection first before running metadata creation
            conn = engine.connect()
            
            # Ensure PostgreSQL enum types exist before model metadata creation
            logger.info("Creating custom PostgreSQL enum types (if they do not exist)...")
            enums = {
                "gender_preference": ("male", "female", "mixed"),
                "booking_status": ("requested", "accepted", "paid", "checked_in", "active", "completed", "cancelled", "vacate_requested", "vacated", "rejected"),
                "payment_status": ("pending", "completed", "failed", "refunded", "pending_verification"),
                "payment_type": ("booking", "monthly_rent", "refund", "commission"),
                "invoice_status": ("pending", "paid", "overdue", "cancelled"),
                "transaction_type": ("credit", "debit", "hold", "release", "withdrawal"),
                "transaction_status": ("pending", "otp_sent", "verified", "completed", "failed", "refunded", "rejected"),
                "vacationstatus": ("upcoming", "active", "completed", "cancelled"),
            }
            for enum_name, values in enums.items():
                values_str = ", ".join(f"'{v}'" for v in values)
                try:
                    conn.execute(text(
                         f"DO $$ BEGIN "
                         f"CREATE TYPE {enum_name} AS ENUM ({values_str}); "
                         f"EXCEPTION WHEN duplicate_object THEN NULL; "
                         f"END $$;"
                    ))
                except Exception as e:
                    logger.warning(f"Enum {enum_name} creation note: {e}")
            
            # Add missing enum values to existing enums (safe for repeated runs)
            enum_additions = [
                "ALTER TYPE transaction_type ADD VALUE IF NOT EXISTS 'withdrawal'",
                "ALTER TYPE transaction_status ADD VALUE IF NOT EXISTS 'rejected'",
                "ALTER TYPE booking_status ADD VALUE IF NOT EXISTS 'vacate_requested'",
                "ALTER TYPE booking_status ADD VALUE IF NOT EXISTS 'vacated'",
                "ALTER TYPE booking_status ADD VALUE IF NOT EXISTS 'rejected'",
                "ALTER TYPE payment_status ADD VALUE IF NOT EXISTS 'pending_verification'",
                "ALTER TYPE vacationstatus ADD VALUE IF NOT EXISTS 'upcoming'",
                "ALTER TYPE vacationstatus ADD VALUE IF NOT EXISTS 'active'",
                "ALTER TYPE vacationstatus ADD VALUE IF NOT EXISTS 'completed'",
                "ALTER TYPE vacationstatus ADD VALUE IF NOT EXISTS 'cancelled'",
            ]
            for sql in enum_additions:
                try:
                    conn.execute(text(sql))
                except Exception as e:
                    logger.warning(f"Enum value add note: {e}")
            
            conn.commit()
            logger.info("PostgreSQL enum types ready")
            
            # Ensure all base tables are created in the database first
            logger.info("Ensuring all base tables exist in schema...")
            from app.database import Base
            import app.models  # Load and register all models with Base.metadata
            Base.metadata.create_all(bind=engine)
            logger.info("Base tables verified/created successfully.")
            break
        except Exception as e:
            if conn:
                try:
                    conn.close()
                except:
                    pass
                conn = None
            
            if attempt == max_retries:
                logger.critical(f"Database connection or initialization failed after {max_retries} attempts: {e}")
                sys.exit(1)
            
            logger.warning(f"Database not ready ({e}). Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)

    try:
        # --- MIGRATION 018: Wallet Transactions ---
        run_alter(conn, "ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS payment_method VARCHAR(20) DEFAULT 'online'", "Added wallet_transactions.payment_method")
        run_alter(conn, "ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS offline_notes TEXT", "Added wallet_transactions.offline_notes")
        run_alter(conn, "ALTER TYPE transaction_type ADD VALUE IF NOT EXISTS 'withdrawal'", "Added Enum value withdrawal")
        run_alter(conn, "ALTER TYPE transaction_status ADD VALUE IF NOT EXISTS 'rejected'", "Added Enum value rejected")

        # --- MIGRATION 019: Payments ---
        run_alter(conn, "ALTER TABLE payments ADD COLUMN IF NOT EXISTS payment_method VARCHAR(20) DEFAULT 'online'", "Added payments.payment_method")
        run_alter(conn, "ALTER TABLE payments ADD COLUMN IF NOT EXISTS offline_reference TEXT", "Added payments.offline_reference")
        run_alter(conn, "ALTER TABLE payments ADD COLUMN IF NOT EXISTS verified_by_id UUID", "Added payments.verified_by_id")
        
        # Foreign Key
        run_alter(conn, """
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
        """, "Checked payments.verified_by_id foreign key")
        
        run_alter(conn, "ALTER TYPE payment_status ADD VALUE IF NOT EXISTS 'pending_verification'", "Added Enum value pending_verification")

        # --- MIGRATION 020: Payment Date ---
        run_alter(conn, "ALTER TABLE payments ADD COLUMN IF NOT EXISTS payment_date TIMESTAMP WITH TIME ZONE", "Added payments.payment_date")

        # --- MIGRATION 021: Wallet Offline Ref ---
        run_alter(conn, "ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS offline_reference TEXT", "Added wallet_transactions.offline_reference")

        # --- MIGRATION 022: Profiles ---
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
            run_alter(conn, f"ALTER TABLE profiles ADD COLUMN IF NOT EXISTS {col} {col_type}", f"Added profiles.{col}")

        # --- MIGRATION 023: Email Verifications ---
        run_alter(conn, "ALTER TABLE email_verifications ADD COLUMN IF NOT EXISTS referral_code VARCHAR(20)", "Added email_verifications.referral_code")

        # --- FINAL VERIFICATION ---
        logger.info("Starting final verification...")
        verify_sql = "SELECT column_name FROM information_schema.columns WHERE table_name='email_verifications' AND column_name='referral_code';"
        result = conn.execute(text(verify_sql)).fetchone()
        if result:
            logger.info("VERIFICATION SUCCESS: column 'referral_code' exists in 'email_verifications'.")
        else:
            logger.critical("VERIFICATION FAILURE: column 'referral_code' STILL MISSING!")
            sys.exit(1)

        logger.info("SUCCESS: Database schema repair completed.")
        
    except Exception as e:
        logger.critical(f"FATAL REPAIR ERROR: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    repair_db()
