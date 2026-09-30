"""
Argus Storage — Local filesystem backend.

Copies clip files to a configurable local directory.
Applies a retention policy on startup and periodically thereafter:
files older than retention_days are deleted automatically.

Typical use case: an external USB drive or NAS mount.
"""
from __future__ import annotations

import asyncio
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog

from argus.storage.base import StorageBackend, StorageUploadError

logger = structlog.get_logger(__name__)


class LocalStorageBackend(StorageBackend):
    """
    Copies clips to a local directory and enforces a retention policy.

    The retention sweep runs once on startup and then every 24 hours.
    Files are deleted if their modification time is older than retention_days.
    """

    def __init__(self, storage_path: str | Path, retention_days: int = 30) -> None:
        self._path = Path(storage_path)
        self._retention_days = retention_days
        self._sweep_task: asyncio.Task | None = None

    async def verify_connectivity(self) -> bool:
        """Ensure the storage directory exists and is writable."""
        try:
            self._path.mkdir(parents=True, exist_ok=True)
            test_file = self._path / ".argus_write_test"
            test_file.touch()
            test_file.unlink()
            logger.info(
                "Local storage backend ready",
                path=str(self._path),
                retention_days=self._retention_days,
            )
            # Start background retention sweep
            self._sweep_task = asyncio.create_task(
                self._retention_sweep_loop(),
                name="argus-local-retention",
            )
            return True
        except Exception as exc:
            logger.error(
                "Local storage backend not accessible",
                path=str(self._path),
                error=str(exc),
            )
            return False

    async def upload(self, local_path: str | Path) -> str:
        """
        Copy the file to the configured storage directory.

        Preserves relative subdirectory structure under the storage root.
        Returns the destination path as a string.
        """
        src = Path(local_path)
        if not src.exists():
            raise StorageUploadError(f"Source file not found: {src}")

        dest = self._path / src.name
        dest.parent.mkdir(parents=True, exist_ok=True)

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, shutil.copy2, str(src), str(dest))
            logger.info(
                "File copied to local storage",
                src=str(src),
                dest=str(dest),
                size_bytes=dest.stat().st_size,
            )
            return str(dest)
        except Exception as exc:
            raise StorageUploadError(f"Local copy failed: {exc}") from exc

    async def _retention_sweep_loop(self) -> None:
        """Periodically delete files older than retention_days."""
        while True:
            await self._sweep_once()
            await asyncio.sleep(86_400)  # 24 hours

    async def _sweep_once(self) -> None:
        """Delete all files in storage_path older than retention_days."""
        if not self._path.exists():
            return
        cutoff = datetime.now(UTC) - timedelta(days=self._retention_days)
        deleted = 0
        freed_bytes = 0
        loop = asyncio.get_event_loop()

        def _do_sweep():
            nonlocal deleted, freed_bytes
            for f in self._path.rglob("*"):
                if not f.is_file():
                    continue
                mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=UTC)
                if mtime < cutoff:
                    freed_bytes += f.stat().st_size
                    f.unlink(missing_ok=True)
                    deleted += 1

        await loop.run_in_executor(None, _do_sweep)
        if deleted:
            logger.info(
                "Retention sweep complete",
                deleted_files=deleted,
                freed_mb=round(freed_bytes / 1_048_576, 2),
                retention_days=self._retention_days,
            )
