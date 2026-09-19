"""
Alembic environment configuration for async SQLAlchemy.

Reads database URL from Argus settings so there's a single source of truth.
Supports both online (live migration) and offline (SQL script generation) modes.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# Load Argus models so Alembic can detect schema changes
from argus.database.models import Base

# Alembic Config object
config = context.config

# Set up logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Point Alembic at our ORM metadata
target_metadata = Base.metadata


def get_database_url() -> str:
    """Load the database URL from Argus settings."""
    try:
        from argus.config.settings import get_settings
        return get_settings().database_url
    except Exception:
        # Fallback for when settings can't be loaded (e.g., missing .env in CI)
        return "sqlite+aiosqlite:///./data/argus.db"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — generate SQL script without DB connection."""
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode using an async engine."""
    url = get_database_url()
    connectable = create_async_engine(url)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online migrations — runs async migration in sync context."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
