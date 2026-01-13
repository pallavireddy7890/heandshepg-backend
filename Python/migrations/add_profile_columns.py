"""Add missing profile columns to database."""
from app.database import engine
from sqlalchemy import text

columns_to_add = [
    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS gender VARCHAR(20)",
    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS date_of_birth VARCHAR(20)",
    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS pan_card_url TEXT",
    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS gst_doc_url TEXT",
    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS aadhar_front_url TEXT",
    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS aadhar_back_url TEXT",
    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS college_company_id_url TEXT",
    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS profile_verification_status VARCHAR(20) DEFAULT 'pending'",
    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS email_notifications BOOLEAN DEFAULT TRUE",
    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS sms_notifications BOOLEAN DEFAULT TRUE",
    "ALTER TABLE profiles ADD COLUMN IF NOT EXISTS push_notifications BOOLEAN DEFAULT FALSE",
]

def main():
    conn = engine.connect()
    for sql in columns_to_add:
        try:
            conn.execute(text(sql))
            print(f"Executed: {sql[:50]}...")
        except Exception as e:
            print(f"Error (might already exist): {e}")
    conn.commit()
    conn.close()
    print("Migration completed!")

if __name__ == "__main__":
    main()
