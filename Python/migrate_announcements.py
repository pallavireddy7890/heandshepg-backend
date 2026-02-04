import psycopg2
import sys

def migrate():
    try:
        conn = psycopg2.connect("postgresql://postgres:suprgen123@localhost:5432/heandshepg_db")
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
