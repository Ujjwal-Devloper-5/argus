"""
Shared pytest fixtures for all Argus tests.

Provides:
- `settings`: A fresh Settings instance with test overrides (in-memory DB)
- `db_session`: An async database session with all tables created
- `camera`: A pre-created Camera record in the DB
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from argus.config.settings import Settings, get_settings
from argus.database.engine import close_engine, get_session, init_db, setup_engine
from argus.database.models import Camera


# ---------------------------------------------------------------------------
# Settings override for tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def settings(tmp_path, monkeypatch) -> Settings:
    """
    Override settings for every test:
    - Use in-memory SQLite (no file, no cleanup needed)
    - Disable all external services (LLM, Telegram, etc.)
    - Use tmp_path for storage paths
    """
    # Clear the lru_cache so each test gets a fresh Settings instance
    get_settings.cache_clear()

    monkeypatch.setenv("ARGUS__DATABASE_URL", "sqlite+aiosqlite:///:memory:?uri=true")
    monkeypatch.setenv("ARGUS__LLM__PROVIDER", "disabled")
    monkeypatch.setenv("ARGUS__ALERTS__TELEGRAM__ENABLED", "false")
    monkeypatch.setenv("ARGUS__STORAGE__LOCAL_PATH", str(tmp_path / "clips"))
    monkeypatch.setenv("ARGUS__THUMBNAILS_PATH", str(tmp_path / "events"))
    monkeypatch.setenv("ARGUS__EMBEDDINGS_PATH", str(tmp_path / "embeddings"))
    monkeypatch.setenv("ARGUS__RECORDINGS_PATH", str(tmp_path / "recordings"))

    s = get_settings()
    yield s

    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Database session fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session(settings):
    """
    Set up a fresh in-memory database for each test.
    Creates all tables, yields a session, then disposes engine.
    """
    setup_engine(settings.database_url, echo=False)
    await init_db()

    async with get_session() as session:
        yield session

    await close_engine()


# ---------------------------------------------------------------------------
# Common model fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def camera(db_session) -> Camera:
    """A pre-created Camera record for use in tests."""
    from argus.database.repository import get_or_create_camera
    cam = await get_or_create_camera(db_session, name="test_cam", rtsp_url="rtsp://test/stream")
    return cam
