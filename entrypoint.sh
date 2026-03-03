#!/bin/bash
set -e

echo "[ENTRYPOINT] Running database migrations..."

# Try to run alembic upgrade. If alembic_version table doesn't exist or
# has a mismatch, stamp to latest and skip (startup sync in main.py handles columns)
alembic upgrade head 2>&1 || {
    echo "[ENTRYPOINT] Migration failed, stamping current state..."
    alembic stamp head 2>&1 || echo "[ENTRYPOINT] Stamp also failed (non-fatal)"
}

echo "[ENTRYPOINT] Starting application..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
