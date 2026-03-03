from logging.config import fileConfig
from sqlalchemy import engine_from_config, create_engine
from sqlalchemy import pool
from alembic import context
import sys
from pathlib import Path
import os

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import Base
from app.models import *  # Import all models

config = context.config

# Get database URL from environment or app settings
database_url = os.getenv("DATABASE_URL")
if not database_url:
    try:
        from app.config import get_settings
        settings = get_settings()
        database_url = settings.database_url
    except Exception:
        # Fall back to alembic.ini
        database_url = config.get_main_option("sqlalchemy.url")

# Ensure we use psycopg2 (sync driver) not asyncpg
if database_url and "+asyncpg" in database_url:
    database_url = database_url.replace("+asyncpg", "")

config.set_main_option("sqlalchemy.url", database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    url = config.get_main_option("sqlalchemy.url")
    connectable = create_engine(url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
