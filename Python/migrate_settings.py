"""Add missing columns to system_settings table."""
from app.database import SessionLocal, engine
from sqlalchemy import text


def migrate():
    """Add description column to system_settings table if it doesn't exist."""
    db = SessionLocal()
    
    try:
        # Check if column exists
        result = db.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'system_settings' AND column_name = 'description'
        """))
        
        if not result.fetchone():
            print("Adding 'description' column to system_settings...")
            db.execute(text("ALTER TABLE system_settings ADD COLUMN description TEXT"))
            db.commit()
            print("✅ Column added successfully!")
        else:
            print("Column 'description' already exists.")
            
        # Also check for updated_by column
        result = db.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'system_settings' AND column_name = 'updated_by'
        """))
        
        if not result.fetchone():
            print("Adding 'updated_by' column to system_settings...")
            db.execute(text("ALTER TABLE system_settings ADD COLUMN updated_by UUID REFERENCES users(id) ON DELETE SET NULL"))
            db.commit()
            print("✅ Column added successfully!")
        else:
            print("Column 'updated_by' already exists.")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
