import os
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def run_payout_migration():
    if not DATABASE_URL:
        print("Error: DATABASE_URL not found in environment.")
        return

    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT) # Needed for ALTER TYPE
        cur = conn.cursor()
        
        print("1. Adding missing columns to 'wallet_transactions'...")
        columns_to_add = [
            ("bank_account_number", "VARCHAR(50)"),
            ("bank_ifsc_code", "VARCHAR(20)"),
            ("bank_name", "VARCHAR(255)"),
            ("admin_notes", "TEXT")
        ]
        
        for col_name, col_type in columns_to_add:
            try:
                cur.execute(f"ALTER TABLE wallet_transactions ADD COLUMN IF NOT EXISTS {col_name} {col_type};")
                print(f"  [OK] Column '{col_name}' added or already exists.")
            except Exception as e:
                print(f"  [ERROR] Failed to add column {col_name}: {e}")

        print("\n2. Updating enum types...")
        
        # Adding 'withdrawal' to transaction_type
        try:
            cur.execute("ALTER TYPE transaction_type ADD VALUE IF NOT EXISTS 'withdrawal';")
            print("  [OK] Added 'withdrawal' to transaction_type.")
        except Exception as e:
            print(f"  [-] Note about transaction_type: {e}")

        # Adding 'rejected' to transaction_status
        try:
            cur.execute("ALTER TYPE transaction_status ADD VALUE IF NOT EXISTS 'rejected';")
            print("  [OK] Added 'rejected' to transaction_status.")
        except Exception as e:
            print(f"  [-] Note about transaction_status: {e}")
            
        cur.close()
        conn.close()
        print("\nSUCCESS: Payout migration completed.")
    except Exception as e:
        print(f"\nFAILED: {e}")

if __name__ == "__main__":
    run_payout_migration()
