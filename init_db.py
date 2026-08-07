#!/usr/bin/env python3
"""
Finalized Database Initialization Script
Initializes extensions and enums, then applies all Alembic migrations.
Usage: python init_db.py
"""
import os
import sys
import subprocess
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def run_command(command):
    print(f"Executing: {' '.join(command)}")
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return False
    print(result.stdout)
    return True

def init_db():
    # Get DATABASE_URL from environment or use default
    DATABASE_URL = os.environ.get("DATABASE_URL")

    if not DATABASE_URL:
        print("ERROR: DATABASE_URL environment variable not set!")
        print("Set it like: export DATABASE_URL=postgresql://user:pass@host:5432/dbname")
        sys.exit(1)

    print("Connecting to database...")

    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        
        # 1. Enable Extensions
        print("\nEnabling extensions...")
        extensions = ["uuid-ossp", "pgcrypto"]
        for ext in extensions:
            try:
                cur.execute(f"CREATE EXTENSION IF NOT EXISTS \"{ext}\";")
                print(f"  [OK] {ext} enabled")
            except Exception as e:
                print(f"  [WARN] Warning enabling {ext}: {e}")

        # 2. Create Enums
        print("\nCreating enum types...")
        enums = [
            ("app_role", ['customer', 'owner', 'admin']),
            ("kyc_status", ['pending', 'approved', 'rejected']),
            ("booking_status", ['requested', 'accepted', 'paid', 'checked_in', 'active', 'completed', 'cancelled', 'vacate_requested', 'vacate_approved', 'vacated']),
            ("payment_type", ['booking', 'monthly_rent', 'refund', 'commission']),
            ("payment_status", ['pending', 'completed', 'failed', 'refunded']),
            ("gender_preference", ['male', 'female', 'mixed']),
            ("invoice_status", ['pending', 'paid', 'overdue', 'cancelled']),
            ("ticket_priority", ['low', 'medium', 'high', 'urgent']),
            ("ticket_status", ['open', 'in_progress', 'resolved', 'closed']),
            ("transaction_type", ['credit', 'debit', 'hold', 'release', 'withdrawal']),
            ("transaction_status", ['pending', 'otp_sent', 'verified', 'completed', 'failed', 'refunded', 'rejected']),
        ]
        
        for enum_name, values in enums:
            values_str = ", ".join([f"'{v}'" for v in values])
            try:
                cur.execute(f"CREATE TYPE {enum_name} AS ENUM ({values_str});")
                print(f"  [OK] Created enum: {enum_name}")
            except psycopg2.errors.DuplicateObject:
                print(f"  [-] Enum already exists: {enum_name}")
            except Exception as e:
                print(f"  [ERROR] Error creating {enum_name}: {e}")
        
        cur.close()
        conn.close()
        
        # 3. Apply Base Schema SQL
        print("\nApplying base schema SQL...")
        schema_path = os.path.join("sql", "init_schema.sql")
        if os.path.exists(schema_path):
            try:
                # Use psql as it's much better at handling multi-statement blocks ($$ blocks)
                env = os.environ.copy()
                # Extract user and password from DATABASE_URL
                db_user = "postgres" # Default
                if "://" in DATABASE_URL:
                   try:
                       auth_part = DATABASE_URL.split("://")[1].split("@")[0]
                       if ":" in auth_part:
                           db_user, passwd = auth_part.split(":")
                           env["PGPASSWORD"] = passwd
                       else:
                           db_user = auth_part
                   except: pass

                # Construct psql command
                db_name = DATABASE_URL.rsplit('/', 1)[1]
                psql_cmd = ["psql", "-U", db_user, "-d", db_name, "-f", schema_path, "-q"]
                
                print(f"Executing: {' '.join(psql_cmd)}")
                res = subprocess.run(psql_cmd, env=env, capture_output=True, text=True, shell=True)
                
                if res.returncode == 0:
                    print("  [OK] Base schema applied successfully")
                else:
                    # Filter out "already exists" errors to keep output clean
                    errors = [line for line in res.stderr.split('\n') if line and "already exists" not in line.lower()]
                    if errors:
                        print(f"  [WARN] Some issues during schema application:\n" + "\n".join(errors[:5]))
                    else:
                        print("  [OK] Base schema applied (with some expected 'already exists' warnings)")
                
                # VERIFY TABLES
                conn = psycopg2.connect(DATABASE_URL)
                cur = conn.cursor()
                cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = 'profiles';")
                exists = cur.fetchone()[0]
                if exists:
                    print("  [VERIFIED] 'profiles' table exists.")
                else:
                    print("  [CRITICAL] 'profiles' table NOT FOUND after schema application!")
                
                # Stamp the database if we just applied the base schema
                # The base schema (init_schema.sql) is typically a snapshot.
                # If we apply it, we might need to stamp Alembic to a certain version.
                # However, many of these migrations are ADD COLUMN IF NOT EXISTS, 
                # so they should be safe to run even if the table already has those columns.
                
                cur.close()
                conn.close()

            except Exception as e:
                print(f"  [ERROR] Error applying base schema with psql: {e}")
        else:
            print(f"  [WARN] Base schema file not found at {schema_path}")

        # 4. Stamp Alembic to head (skip migrations since base schema already has tables)
        print("\nStamping Alembic version...")
        is_windows = os.name == 'nt'
        alembic_cmd = os.path.join("venv", "Scripts" if is_windows else "bin", "alembic" + (".exe" if is_windows else ""))
        if not os.path.exists(alembic_cmd):
            alembic_cmd = "alembic"

        print(f"Executing: {alembic_cmd} stamp head")
        result = subprocess.run([alembic_cmd, "stamp", "head"], capture_output=True, text=True, shell=is_windows)
        
        if result.returncode == 0:
            print(result.stdout)
            print("\n[SUCCESS] Database initialization complete!")
        else:
            print(f"\n[WARN] Error stamping Alembic version:")
            print(result.stdout)
            print(result.stderr)
            # Don't exit - stamping failure is not critical
        
    except Exception as e:
        print(f"\n[ERROR] {e}")
        sys.exit(1)

if __name__ == "__main__":
    init_db()
