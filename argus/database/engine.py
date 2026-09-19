"""
Argus Database Engine.

Provides:
- Async SQLAlchemy engine with connection pooling
- `get_session()` async context manager for dependency injection
- `init_db()` to create all tables (used in tests; prod uses Alembic migrations)
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool, StaticPool

import structlog

logger = structlog.get_logger(__name__)

# Module-level engine and session factory — initialized once via `setup_engine()`
_engine = None
_async_session_factory = None


def setup_engine(database_url: str, echo: bool = False) -> None:
    """
    Initialize the async SQLAlchemy engine.

    Must be called once at application startup before any DB operations.

    Args:
        database_url: SQLAlchemy async database URL.
            SQLite:   "sqlite+aiosqlite:///./data/argus.db"
            Postgres: "postgresql+asyncpg://user:pass@host/db"
        echo: If True, log all SQL statements (debug only).
    """
    global _engine, _async_session_factory

    connect_args: dict = {}
    pool_kwargs: dict = {}

    if database_url.startswith("sqlite"):
        # SQLite requires special handling for async:
        # - check_same_thread=False for multi-threaded async access
        # - StaticPool for in-memory DBs used in tests (shared connection)
        connect_args["check_same_thread"] = False
        if ":memory:" in database_url:
            pool_kwargs["poolclass"] = StaticPool
            connect_args["uri"] = True
        # Enable WAL mode for SQLite — better concurrent read performance
        connect_args["timeout"] = 30
    else:
        # PostgreSQL: use NullPool with asyncpg to avoid cross-thread issues
        # Connection pooling is handled by asyncpg itself
        pool_kwargs["poolclass"] = NullPool

    _engine = create_async_engine(
        database_url,
        echo=echo,
        connect_args=connect_args,
        **pool_kwargs,
    )

    _async_session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,  # Don't expire objects after commit (avoids lazy load issues)
        autoflush=False,
        autocommit=False,
    )

    logger.info("Database engine initialized", url=_redact_url(database_url))


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager that provides a database session.

    Commits on success, rolls back on any exception, always closes.

    Usage:
        async with get_session() as session:
            result = await session.execute(select(Camera))
    """
    if _async_session_factory is None:
        raise RuntimeError("Database not initialized. Call setup_engine() first.")

    async with _async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Create all tables from ORM metadata.

    Use this for tests only. Production uses Alembic migrations.
    """
    from argus.database.models import Base  # avoid circular import

    if _engine is None:
        raise RuntimeError("Database not initialized. Call setup_engine() first.")

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.debug("Database tables created from ORM metadata.")


async def close_engine() -> None:
    """Dispose the engine — call on application shutdown."""
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None
        logger.info("Database engine closed.")


def _redact_url(url: str) -> str:
    """Redact password from URL for safe logging."""
    from urllib.parse import urlparse, urlunparse
    try:
        parsed = urlparse(url)
        if parsed.password:
            netloc = parsed.netloc.replace(parsed.password, "***")
            return urlunparse(parsed._replace(netloc=netloc))
    except Exception:
        pass
    return url
