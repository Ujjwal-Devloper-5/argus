"""
Argus AI Security System — Application Entrypoint.

Startup sequence (in order):
  1.  Load and validate Settings
  2.  Configure structured logging
  3.  Print banner
  4.  Run Alembic DB migrations (in executor — non-blocking)
  5.  Setup DB engine
  6.  Start Kafka producer (if enabled)
  7.  Start AlertManager (Telegram + Discord bots)
  8.  Build and start StorageManager (Kafka upload consumer)
  9.  For each active camera: build fully-wired EventOrchestrator
  10. Start StreamWorker + orchestrator run loop tasks
  11. Wait for SIGTERM / SIGINT
  12. Graceful shutdown in reverse dependency order

All subsystems use dependency injection — no global singletons after
Settings is loaded.
"""
from __future__ import annotations

import asyncio
import contextlib
import signal
from pathlib import Path

import structlog

from argus.config import get_settings
from argus.config.logging import configure_logging
from argus.utils.banner import print_banner

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Startup helpers
# ---------------------------------------------------------------------------


async def _run_migrations() -> None:
    """Apply pending Alembic migrations at startup (non-blocking)."""
    try:
        from alembic.config import Config as AlembicConfig

        from alembic import command

        alembic_cfg = AlembicConfig("alembic.ini")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, command.upgrade, alembic_cfg, "head")
        logger.info("Database migrations applied successfully")
    except Exception as exc:
        logger.warning("Alembic migration skipped", error=str(exc))


async def _start_kafka_producer(settings):
    """Initialise and start ArgusProducer. Returns producer or None."""
    if not settings.kafka.enabled:
        logger.info("Kafka disabled — running without event streaming")
        return None
    try:
        from argus.kafka.producer import ArgusProducer

        producer = ArgusProducer(settings)
        await producer.start()
        logger.info("Kafka producer started", bootstrap=settings.kafka.bootstrap_servers)
        return producer
    except Exception as exc:
        logger.warning(
            "Kafka producer failed to start — continuing without Kafka",
            error=str(exc),
        )
        return None


async def _start_storage_manager(settings, producer, session_factory):
    """Build and start StorageManager if storage is configured."""
    storage_cfg = settings.storage
    try:
        from argus.kafka.consumer import ArgusConsumer
        from argus.kafka.topics import ArgusConsumerGroups, ArgusTopics
        from argus.storage.manager import StorageManager

        if storage_cfg.backend == "rclone":
            if not storage_cfg.rclone_remote:
                logger.warning("rclone backend selected but rclone_remote not configured — skipping")
                return None
            from argus.storage.rclone import RcloneBackend

            remote = f"{storage_cfg.rclone_remote}:{storage_cfg.rclone_path or ''}"
            backend = RcloneBackend(remote=remote.rstrip(":"))
        else:
            from argus.storage.local import LocalStorageBackend

            backend = LocalStorageBackend(
                storage_path=storage_cfg.local_path,
                retention_days=storage_cfg.retention_days,
            )

        # Placeholder manager — consumer attached below
        manager = StorageManager(
            backend=backend,
            producer=producer,
            consumer=None,  # type: ignore[arg-type]
            session_factory=session_factory,
        )

        if producer and settings.kafka.enabled:
            consumer = ArgusConsumer(
                settings=settings,
                topics=[ArgusTopics.UPLOADS],
                group_id=ArgusConsumerGroups.STORAGE_WORKERS,
                handler=manager.handle_upload_message,
                producer=producer,
            )
            await consumer.start()
            manager._consumer = consumer
            await manager.start()
            logger.info("StorageManager started", backend=storage_cfg.backend)
        else:
            logger.info("StorageManager skipped — Kafka not available")
            return None

        return manager
    except Exception as exc:
        logger.warning("StorageManager failed to start", error=str(exc))
        return None


async def _build_camera_orchestrator(
    camera,
    settings,
    alert_manager,
    kafka_producer,
    storage_manager,
    session_factory,
):
    """Build a fully-wired EventOrchestrator for one camera."""
    from argus.core.detector import DetectorWorker
    from argus.core.motion import MotionFilter
    from argus.core.recognizer import FaceRecognizer
    from argus.core.recorder import EventRecorder
    from argus.core.stream import StreamWorker
    from argus.core.tracker import SortTracker
    from argus.intelligence.embeddings import EmbeddingDB
    from argus.intelligence.factory import LLMProviderFactory
    from argus.intelligence.learner import AutoLearner
    from argus.pipeline.orchestrator import EventOrchestrator

    # Stream worker (RTSP → frame queue)
    stream = StreamWorker(camera)

    # Motion filter (camera-specific thresholds)
    motion = MotionFilter.from_camera(camera)

    # YOLO detector
    detector = DetectorWorker(settings.detection)

    # SORT tracker (one per camera, stateful)
    tracker = SortTracker()

    # Face recognition (InsightFace + FAISS)
    embedding_db = EmbeddingDB(settings)
    recognizer = FaceRecognizer.from_config(settings.recognition, db=embedding_db)

    # Clip recorder (FFmpeg, NVENC-accelerated)
    clip_dir = Path(settings.recordings_path) / camera.name
    clip_dir.mkdir(parents=True, exist_ok=True)
    recorder = EventRecorder(
        output_dir=str(clip_dir),
        fps=camera.fps,
        camera_name=camera.name,
    )

    # LLM provider (Ollama / OpenAI / Anthropic / Gemini / Disabled)
    llm_provider = LLMProviderFactory.create(settings.llm)

    # Laya 421M fast decision gate (optional)
    laya_gate = None
    if settings.llm.laya.enabled:
        with contextlib.suppress(Exception):
            laya_gate = LLMProviderFactory.create_laya_gate(settings)

    # AutoLearner
    learner = AutoLearner(
        session_factory=session_factory,
        alert_manager=alert_manager,
        settings=settings,
        embedding_db=embedding_db,
    )

    orchestrator = EventOrchestrator(
        camera=camera,
        stream_worker=stream,
        motion_filter=motion,
        detector=detector,
        tracker=tracker,
        recognizer=recognizer,
        recorder=recorder,
        alert_manager=alert_manager,
        learner=learner,
        llm_provider=llm_provider,
        laya_gate=laya_gate,
        kafka_producer=kafka_producer,
        storage_manager=storage_manager,
        session_factory=session_factory,
        settings=settings,
    )

    await orchestrator.start()
    return orchestrator, stream


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------


async def main() -> None:
    """Full Argus application lifecycle."""

    # ── 1. Settings + logging ────────────────────────────────────────────
    settings = get_settings()
    configure_logging(settings)
    print_banner()

    logger.info(
        "Argus starting",
        version="0.8.0",
        phase=8,
        cameras=len(settings.cameras),
        kafka_enabled=settings.kafka.enabled,
    )

    # ── 2. DB migrations ─────────────────────────────────────────────────
    await _run_migrations()

    # ── 3. DB engine + session factory ───────────────────────────────────
    from argus.database.engine import get_session, setup_engine

    setup_engine(settings.database_url, echo=settings.debug)
    session_factory = get_session

    # ── 4. Kafka producer ────────────────────────────────────────────────
    kafka_producer = await _start_kafka_producer(settings)

    # ── 5. AlertManager (Telegram + Discord) ─────────────────────────────
    from argus.alerts.manager import AlertManager

    alert_manager = AlertManager(settings)
    await alert_manager.start()

    # ── 6. StorageManager ────────────────────────────────────────────────
    storage_manager = await _start_storage_manager(
        settings, kafka_producer, session_factory
    )

    # ── 7. Build per-camera orchestrators ────────────────────────────────
    active_cameras = [c for c in settings.cameras if not c.disabled]
    if not active_cameras:
        logger.warning("No active cameras configured — Argus running idle")

    orchestrators: list = []
    stream_workers: list = []

    for camera in active_cameras:
        try:
            orch, stream = await _build_camera_orchestrator(
                camera=camera,
                settings=settings,
                alert_manager=alert_manager,
                kafka_producer=kafka_producer,
                storage_manager=storage_manager,
                session_factory=session_factory,
            )
            orchestrators.append(orch)
            stream_workers.append(stream)
            logger.info("Camera pipeline ready", camera=camera.name, rtsp=camera.rtsp_url)
        except Exception as exc:
            logger.error(
                "Failed to build pipeline for camera",
                camera=camera.name,
                error=str(exc),
            )

    # ── 8. Launch stream workers + orchestrator run loops ─────────────────
    async def _run_camera(orch, stream) -> None:
        cam = orch._camera.name
        try:
            await stream.start()
            await orch.run()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("Camera pipeline crashed", camera=cam, error=str(exc))
        finally:
            with contextlib.suppress(Exception):
                await stream.stop()
            with contextlib.suppress(Exception):
                await orch.stop()

    pipeline_tasks = [
        asyncio.create_task(
            _run_camera(orch, stream),
            name=f"argus-cam-{orch._camera.name}",
        )
        for orch, stream in zip(orchestrators, stream_workers, strict=True)
    ]

    logger.info(
        "Argus is running",
        active_cameras=len(active_cameras),
        kafka=kafka_producer is not None,
        storage=storage_manager is not None,
    )

    # ── 9. Wait for shutdown signal ───────────────────────────────────────
    stop_event = asyncio.Event()

    def _on_signal(sig: signal.Signals) -> None:
        logger.info("Shutdown signal received", signal=sig.name)
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _on_signal, sig)

    await stop_event.wait()

    # ── 10. Graceful shutdown (reverse order) ────────────────────────────
    logger.info("Shutting down gracefully...")

    # Cancel pipeline tasks
    for task in pipeline_tasks:
        task.cancel()
    with contextlib.suppress(Exception):
        await asyncio.gather(*pipeline_tasks, return_exceptions=True)

    # Stop storage manager
    if storage_manager:
        with contextlib.suppress(Exception):
            await storage_manager.stop()

    # Stop alert manager
    with contextlib.suppress(Exception):
        await alert_manager.stop()

    # Flush and stop Kafka producer
    if kafka_producer:
        with contextlib.suppress(Exception):
            await kafka_producer.stop()

    # Close DB connections
    from argus.database.engine import close_engine

    with contextlib.suppress(Exception):
        await close_engine()

    logger.info("Argus shut down cleanly")


if __name__ == "__main__":
    asyncio.run(main())
