import sys
import os
from sqlalchemy import create_engine, text

# Add current directory to sys.path
sys.path.append(os.getcwd())

from app.database import engine, DATABASE_URL

def verify_query():
    print(f"Testing raw SQL query on DATABASE_URL: {DATABASE_URL}")
    with engine.connect() as conn:
        try:
            # Try to fetch one row with the is_deleted column
            result = conn.execute(text("SELECT id, content, is_deleted FROM roommate_messages LIMIT 1;"))
            row = result.fetchone()
            if row:
                print(f"Success! Row data: {row}")
            else:
                print("Table is empty, but query worked.")
        except Exception as e:
            print(f"Query FAILED: {e}")

if __name__ == "__main__":
    verify_query()
