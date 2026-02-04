import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def run_migration():
    if not DATABASE_URL:
        print("Error: DATABASE_URL not found in environment.")
        return

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        print("Applying migration: Add security_deposit column to rooms table...")
        cur.execute("ALTER TABLE rooms ADD COLUMN IF NOT EXISTS security_deposit INTEGER;")
        
        conn.commit()
        cur.close()
        conn.close()
        print("SUCCESS: Migration applied.")
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    run_migration()
