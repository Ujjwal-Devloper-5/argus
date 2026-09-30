"""
Argus Storage — Abstract backend interface.

All storage backends implement this ABC.
The StorageManager uses this interface exclusively — never imports
concrete backends directly, enabling zero-code backend switching.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class StorageBackend(ABC):
    """
    Abstract base class for all Argus storage backends.

    Implementations must be async-safe and never block the event loop.
    All heavy I/O (file copy, network upload) must use either:
      - asyncio.create_subprocess_exec  (for external tools like rclone)
      - asyncio.run_in_executor         (for blocking Python I/O)
    """

    @abstractmethod
    async def upload(self, local_path: str | Path) -> str:
        """
        Upload a local file to this backend.

        Args:
            local_path: Absolute path to the local file.

        Returns:
            Remote URL or path string. Empty string if URL is unavailable.

        Raises:
            StorageUploadError: If the upload fails after all retries.
        """

    @abstractmethod
    async def verify_connectivity(self) -> bool:
        """
        Check that this backend is reachable and configured correctly.
        Called at startup — logs a clear error and returns False if misconfigured.
        """


class StorageUploadError(Exception):
    """Raised when a storage backend upload fails unrecoverably."""
