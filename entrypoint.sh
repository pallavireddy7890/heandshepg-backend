#!/bin/bash
set -e

echo "[ENTRYPOINT] Running database repair and migrations..."
python scripts/repair_db_production.py

# Try to run alembic upgrade. 
alembic upgrade head || {
    echo "[ENTRYPOINT] Migration failed. Check logs for details."
    # We no longer 'stamp head' automatically because it can lead to silent schema gaps.
    # Manual intervention is preferred if migrations fail.
}

echo "[ENTRYPOINT] Starting application..."
# Use $PORT from environment (default to 8000 if not set)
PORT=${PORT:-8000}
exec uvicorn app.main:app --host 0.0.0.0 --port $PORT
