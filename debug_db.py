import sys
import os
from sqlalchemy import create_engine, text, inspect

# Add current directory to sys.path
sys.path.append(os.getcwd())

from app.database import engine

def debug_schema():
    print("Checking database schema...")
    inspector = inspect(engine)
    columns = [c['name'] for c in inspector.get_columns('roommate_messages')]
    print(f"Current columns in roommate_messages: {columns}")
    
    if 'is_deleted' not in columns:
        print("Column 'is_deleted' is missing. Attempting to add...")
        with engine.connect() as conn:
            try:
                conn.execute(text("ALTER TABLE roommate_messages ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE;"))
                conn.commit()
                print("Successfully added is_deleted column.")
            except Exception as e:
                print(f"Error adding column: {e}")
                conn.rollback()
    else:
        print("Column 'is_deleted' already exists.")

    # Re-check
    columns = [c['name'] for c in inspector.get_columns('roommate_messages')]
    print(f"Final columns in roommate_messages: {columns}")

if __name__ == "__main__":
    debug_schema()
