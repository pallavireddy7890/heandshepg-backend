import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def check_columns():
    if not DATABASE_URL:
        print("Error: DATABASE_URL not found in environment.")
        return

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        cur.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'wallet_transactions';
        """)
        
        columns = cur.fetchall()
        print("Columns in 'wallet_transactions':")
        for col in columns:
            print(f"- {col[0]} ({col[1]})")
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error checking columns: {e}")

if __name__ == "__main__":
    check_columns()
