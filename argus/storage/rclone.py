"""
Argus Storage — rclone multi-cloud backend.

All cloud targets (Google Drive, AWS S3, Cloudflare R2, Backblaze B2, SFTP)
are handled by a single RcloneBackend class via the rclone binary.

Requires rclone to be installed and configured on the host.
See: https://rclone.org/install/

Rclone is called via asyncio.create_subprocess_exec — fully async,
the event loop is never blocked.
"""
from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import structlog

from argus.storage.base import StorageBackend, StorageUploadError

logger = structlog.get_logger(__name__)


class RcloneBackend(StorageBackend):
    """
    Upload files to any rclone-supported cloud backend.

    `remote` is the rclone remote + path, e.g.:
      - "gdrive:Security/Argus/clips"
      - "s3:my-bucket/argus"
      - "b2:my-bucket/clips"
      - "sftp:nas/argus"
    """

    def __init__(
        self,
        remote: str,
        rclone_bin: str = "rclone",
        extra_flags: list[str] | None = None,
        timeout_seconds: int = 300,
    ) -> None:
        self._remote = remote
        self._rclone_bin = rclone_bin
        self._extra_flags = extra_flags or []
        self._timeout = timeout_seconds

    async def verify_connectivity(self) -> bool:
        """Check that rclone binary exists and the remote is accessible."""
        # Check binary
        if not shutil.which(self._rclone_bin):
            logger.error(
                "rclone binary not found",
                binary=self._rclone_bin,
                hint="Install rclone: https://rclone.org/install/",
            )
            return False

        # Check remote connectivity with 'rclone lsd'
        try:
            proc = await asyncio.create_subprocess_exec(
                self._rclone_bin, "lsd", self._remote,
                "--max-depth", "1",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            if proc.returncode != 0:
                logger.warning(
                    "rclone remote check failed",
                    remote=self._remote,
                    stderr=stderr.decode().strip(),
                )
                return False
            logger.info("rclone backend ready", remote=self._remote)
            return True
        except TimeoutError:
            logger.error("rclone remote check timed out", remote=self._remote)
            return False
        except Exception as exc:
            logger.error("rclone remote check error", error=str(exc))
            return False

    async def upload(self, local_path: str | Path) -> str:
        """
        Upload a single file to the configured rclone remote.

        Uses 'rclone copyto' to upload exactly one file (not a directory).
        Returns the remote URL obtained via 'rclone link', or the remote path
        if the backend does not support public links.
        """
        src = Path(local_path)
        if not src.exists():
            raise StorageUploadError(f"Source file not found: {src}")

        remote_dest = f"{self._remote}/{src.name}"
        cmd = [
            self._rclone_bin,
            "copyto",
            str(src),
            remote_dest,
            "--progress",
            "--stats-one-line",
            *self._extra_flags,
        ]

        logger.info("rclone upload starting", src=str(src), remote=remote_dest)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout
            )

            if proc.returncode != 0:
                err_msg = stderr.decode().strip()
                raise StorageUploadError(
                    f"rclone exited {proc.returncode}: {err_msg}"
                )

            logger.info(
                "rclone upload complete",
                src=str(src),
                remote=remote_dest,
            )

            # Attempt to get a public link
            return await self._get_link(remote_dest)

        except TimeoutError as exc:
            raise StorageUploadError(
                f"rclone upload timed out after {self._timeout}s"
            ) from exc

    async def _get_link(self, remote_path: str) -> str:
        """Try 'rclone link' to get a shareable URL. Returns remote_path on failure."""
        try:
            proc = await asyncio.create_subprocess_exec(
                self._rclone_bin, "link", remote_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15.0)
            if proc.returncode == 0:
                url = stdout.decode().strip()
                if url:
                    return url
        except Exception:
            pass
        return remote_path
