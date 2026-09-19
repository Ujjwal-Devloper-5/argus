"""
Argus Logging Configuration.

Configures structlog with:
- JSON output in production (LOG_FORMAT=json) — machine-parseable, for log aggregators
- Pretty colored output in development (LOG_FORMAT=pretty) — human-readable

Usage:
    from argus.config.logging import configure_logging
    configure_logging(log_level="INFO", log_format="pretty")

    import structlog
    logger = structlog.get_logger(__name__)
    logger.info("Event detected", camera="front_door", face_id=42)
"""

from __future__ import annotations

import logging
import sys
from typing import Literal

import structlog


def configure_logging(
    log_level: str = "INFO",
    log_format: Literal["pretty", "json"] = "pretty",
) -> None:
    """
    Configure structlog and the stdlib logging bridge.

    Must be called once at application startup before any loggers are used.
    """
    # Shared processors run on every log event regardless of renderer
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if log_format == "json":
        # Production: structured JSON — every field is a key-value pair
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
        formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                renderer,
            ],
        )
    else:
        # Development: colored, human-readable console output
        renderer = structlog.dev.ConsoleRenderer(colors=True)
        formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                renderer,
            ],
        )

    # Apply formatter to the root stdlib handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Silence noisy third-party libraries in production
    for noisy_lib in ["httpx", "httpcore", "urllib3", "asyncio"]:
        logging.getLogger(noisy_lib).setLevel(logging.WARNING)

    # Wire structlog to use stdlib as the backend
    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
