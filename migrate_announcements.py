import psycopg2
import sys
import os

def migrate():
    try:
        database_url = os.environ.get("DATABASE_URL", "postgresql://postgres:password@localhost:5432/heandshepg_db")
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
        
        print("Adding target_audience column...")
        cur.execute("ALTER TABLE announcements ADD COLUMN IF NOT EXISTS target_audience VARCHAR(20) DEFAULT 'all';")
        
        print("Adding is_admin column...")
        cur.execute("ALTER TABLE announcements ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE;")
        
        conn.commit()
        cur.close()
        conn.close()
        print("Migration successful")
    except Exception as e:
        print(f"Migration failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    migrate()
