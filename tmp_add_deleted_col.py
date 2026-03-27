import sys
import os
from sqlalchemy import create_engine, text

# Add current directory to sys.path
sys.path.append(os.getcwd())

from app.database import engine

def add_column():
    with engine.connect() as conn:
        try:
            # Check if column already exists
            result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='roommate_messages' AND column_name='is_deleted';"))
            if result.fetchone():
                print("Column 'is_deleted' already exists.")
                return

            conn.execute(text("ALTER TABLE roommate_messages ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE;"))
            conn.commit()
            print("Successfully added is_deleted column to roommate_messages table.")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    add_column()
