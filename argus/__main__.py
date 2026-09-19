"""
Argus application entrypoint.

Run with:
    python -m argus
    argus start   (via CLI)
"""

from __future__ import annotations

import asyncio
import signal
import sys

import structlog

logger = structlog.get_logger(__name__)


async def main() -> None:
    """Bootstrap and run the Argus system."""
    # 1. Load and validate configuration (fails loudly if invalid)
    from argus.config.logging import configure_logging
    from argus.config.settings import get_settings

    settings = get_settings()
    configure_logging(log_level=settings.log_level, log_format=settings.log_format)

    logger.info(
        "Argus starting",
        version="0.1.0",
        cameras=len(settings.cameras),
        llm_provider=settings.llm.provider,
        device=settings.detection.device,
    )

    # 2. Initialize database
    from argus.database.engine import setup_engine
    setup_engine(settings.database_url, echo=settings.debug)
    logger.info("Database initialized", url=settings.database_url.split("///")[-1])

    # 3. Ensure DB schema is up-to-date via Alembic
    try:
        from alembic import command
        from alembic.config import Config as AlembicConfig
        alembic_cfg = AlembicConfig("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations applied.")
    except Exception as exc:
        logger.warning("Alembic migration skipped", error=str(exc))

    # 4. Pipeline initialization will go here in Phase 8
    logger.info("Argus initialized successfully. Pipeline coming in Phase 8.")

    # 5. Wait for shutdown signal
    stop_event = asyncio.Event()

    def _handle_signal(sig: signal.Signals) -> None:
        logger.info("Shutdown signal received", signal=sig.name)
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _handle_signal, sig)

    await stop_event.wait()

    # 6. Graceful shutdown
    from argus.database.engine import close_engine
    await close_engine()
    logger.info("Argus shut down cleanly.")


if __name__ == "__main__":
    asyncio.run(main())
