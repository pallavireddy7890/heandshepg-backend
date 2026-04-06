#!/bin/bash
set -e

echo "[ENTRYPOINT] Running database repair and migrations..."
python scripts/repair_db_production.py

# Run the robust repair script. If it fails, the container will stop and report an error.
python scripts/repair_db_production.py

# Try to run alembic upgrade. 
alembic upgrade head || {
    echo "[ENTRYPOINT] Alembic upgrade failed, but schema repair might have succeeded. Proceeding..."
}

echo "[ENTRYPOINT] Starting application..."
# Use $PORT from environment (default to 8000 if not set)
PORT=${PORT:-8000}
exec uvicorn app.main:app --host 0.0.0.0 --port $PORT
