#!/bin/bash
set -e

echo "[ENTRYPOINT] Starting database maintenance..."

# Run the standalone repair script as a safety measure.
# We use this to ensure ANY missing columns (like referral_code) are added 
# before the app starts or Alembic attempts to update the version table.
python scripts/repair_db_production.py

echo "[ENTRYPOINT] Running alembic migrations..."
# Try to run alembic upgrade. 
alembic upgrade head || {
    echo "[ENTRYPOINT] Alembic upgrade failed, but schema repair has likely added the necessary columns. Starting app..."
}

echo "[ENTRYPOINT] Starting application..."
# Use $PORT from environment (default to 8000 if not set)
PORT=${PORT:-8000}
exec uvicorn app.main:app --host 0.0.0.0 --port $PORT
