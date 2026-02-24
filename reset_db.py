"""Quick script to drop and recreate database."""
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

# Connect to postgres database (not heandshepg_db)
engine = create_engine('postgresql://postgres:suprgen123@localhost:5432/postgres', isolation_level="AUTOCOMMIT")

try:
    with engine.connect() as conn:
        # Terminate all connections
        conn.execute(text("""
            SELECT pg_terminate_backend(pg_stat_activity.pid) 
            FROM pg_stat_activity 
            WHERE pg_stat_activity.datname = 'heandshepg_db' 
            AND pid <> pg_backend_pid()
        """))
        print("Terminated all connections")
        
        # Drop database
        conn.execute(text("DROP DATABASE IF EXISTS heandshepg_db"))
        print("Dropped database")
        
        # Create database
        conn.execute(text("CREATE DATABASE heandshepg_db"))
        print("Created database")
        
    print("\nDatabase reset complete! Now run: python init_db.py")
except Exception as e:
    print(f"Error: {e}")
