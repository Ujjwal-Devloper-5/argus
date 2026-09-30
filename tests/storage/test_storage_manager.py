"""
Tests for Phase 7: Argus Storage Manager — local backend, rclone backend, Kafka integration.
All external I/O (rclone, Kafka, DB, filesystem) is mocked.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from argus.storage.base import StorageBackend, StorageUploadError
from argus.storage.local import LocalStorageBackend
from argus.storage.rclone import RcloneBackend
from argus.storage.manager import StorageManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_storage(tmp_path):
    """Return a LocalStorageBackend pointing at a temp directory."""
    return LocalStorageBackend(storage_path=tmp_path / "clips", retention_days=7)


@pytest.fixture
def sample_clip(tmp_path) -> Path:
    """Create a fake MP4 clip file."""
    clip = tmp_path / "event-42.mp4"
    clip.write_bytes(b"fake_mp4_bytes" * 100)
    return clip


@pytest.fixture
def mock_producer():
    p = AsyncMock()
    p.is_started = True
    p.publish = AsyncMock()
    return p


@pytest.fixture
def mock_consumer():
    c = AsyncMock()
    c.start = AsyncMock()
    c.stop = AsyncMock()
    c.consume = AsyncMock()  # Doesn't actually loop in tests
    return c


@pytest.fixture
def manager(mock_producer, mock_consumer):
    backend = MagicMock(spec=StorageBackend)
    backend.verify_connectivity = AsyncMock(return_value=True)
    backend.upload = AsyncMock(return_value="https://example.com/clip.mp4")
    return StorageManager(
        backend=backend,
        producer=mock_producer,
        consumer=mock_consumer,
    )


# ---------------------------------------------------------------------------
# StorageBackend ABC
# ---------------------------------------------------------------------------

def test_storage_backend_is_abstract():
    with pytest.raises(TypeError):
        StorageBackend()  # Cannot instantiate abstract class


def test_storage_upload_error_is_exception():
    exc = StorageUploadError("upload failed")
    assert str(exc) == "upload failed"
    assert isinstance(exc, Exception)


# ---------------------------------------------------------------------------
# LocalStorageBackend
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_local_backend_verify_creates_directory(tmp_path, tmp_storage):
    with patch.object(tmp_storage, '_retention_sweep_loop', new_callable=AsyncMock):
        result = await tmp_storage.verify_connectivity()
    assert result is True
    storage_dir = tmp_path / "clips"
    assert storage_dir.exists()


@pytest.mark.asyncio
async def test_local_backend_upload_copies_file(tmp_storage, sample_clip):
    with patch.object(tmp_storage, '_retention_sweep_loop', new_callable=AsyncMock):
        await tmp_storage.verify_connectivity()
    dest = await tmp_storage.upload(sample_clip)
    assert Path(dest).exists()
    assert Path(dest).read_bytes() == sample_clip.read_bytes()


@pytest.mark.asyncio
async def test_local_backend_upload_raises_for_missing_file(tmp_storage, tmp_path):
    with patch.object(tmp_storage, '_retention_sweep_loop', new_callable=AsyncMock):
        await tmp_storage.verify_connectivity()
    missing = tmp_path / "nonexistent.mp4"
    with pytest.raises(StorageUploadError, match="not found"):
        await tmp_storage.upload(missing)


@pytest.mark.asyncio
async def test_local_backend_retention_deletes_old_files(tmp_path):
    import time, os
    backend = LocalStorageBackend(storage_path=tmp_path / "clips", retention_days=0)
    with patch.object(backend, '_retention_sweep_loop', new_callable=AsyncMock):
        await backend.verify_connectivity()
    # Create a file and manually backdate its mtime
    old_clip = (tmp_path / "clips" / "old.mp4")
    old_clip.write_bytes(b"old")
    old_time = time.time() - (2 * 86400)  # 2 days old
    os.utime(str(old_clip), (old_time, old_time))
    # Run one sweep
    await backend._sweep_once()
    assert not old_clip.exists()


@pytest.mark.asyncio
async def test_local_backend_retention_keeps_new_files(tmp_path):
    backend = LocalStorageBackend(storage_path=tmp_path / "clips", retention_days=30)
    with patch.object(backend, '_retention_sweep_loop', new_callable=AsyncMock):
        await backend.verify_connectivity()
    new_clip = tmp_path / "clips" / "new.mp4"
    new_clip.write_bytes(b"new")
    await backend._sweep_once()
    assert new_clip.exists()


# ---------------------------------------------------------------------------
# RcloneBackend
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rclone_verify_fails_if_binary_missing():
    backend = RcloneBackend(remote="gdrive:test", rclone_bin="rclone_nonexistent_binary")
    with patch("argus.storage.rclone.shutil.which", return_value=None):
        result = await backend.verify_connectivity()
    assert result is False


@pytest.mark.asyncio
async def test_rclone_upload_success(sample_clip):
    backend = RcloneBackend(remote="gdrive:Security/Argus", timeout_seconds=30)

    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))

    mock_link_proc = AsyncMock()
    mock_link_proc.returncode = 0
    mock_link_proc.communicate = AsyncMock(return_value=(b"https://drive.google.com/file/abc", b""))

    with patch("argus.storage.rclone.asyncio.create_subprocess_exec",
               side_effect=[mock_proc, mock_link_proc]):
        result = await backend.upload(sample_clip)

    assert "https://" in result


@pytest.mark.asyncio
async def test_rclone_upload_raises_on_nonzero_exit(sample_clip):
    backend = RcloneBackend(remote="gdrive:Security/Argus", timeout_seconds=30)

    mock_proc = AsyncMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"", b"connection refused"))

    with patch("argus.storage.rclone.asyncio.create_subprocess_exec", return_value=mock_proc):
        with pytest.raises(StorageUploadError, match="rclone exited 1"):
            await backend.upload(sample_clip)


@pytest.mark.asyncio
async def test_rclone_upload_raises_for_missing_file():
    backend = RcloneBackend(remote="gdrive:Security/Argus")
    with pytest.raises(StorageUploadError, match="not found"):
        await backend.upload("/nonexistent/clip.mp4")


# ---------------------------------------------------------------------------
# StorageManager
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_storage_manager_start_verifies_backend(manager):
    await manager.start()
    manager._backend.verify_connectivity.assert_called_once()
    await manager.stop()


@pytest.mark.asyncio
async def test_storage_manager_enqueue_publishes_to_kafka(manager, sample_clip):
    await manager.start()
    await manager.enqueue(local_path=sample_clip, event_id=42, camera_name="front_door")
    await manager.stop()

    manager._producer.publish.assert_called_once()
    call_kwargs = manager._producer.publish.call_args
    # Verify topic and event_id key
    assert "argus.uploads" in str(call_kwargs)
    assert "42" in str(call_kwargs)


@pytest.mark.asyncio
async def test_handle_upload_calls_backend(manager, sample_clip):
    payload = {
        "path": str(sample_clip),
        "event_id": 99,
        "camera": "back_door",
        "enqueued_at": "2026-01-01T00:00:00+00:00",
    }
    await manager.handle_upload_message(payload)
    manager._backend.upload.assert_called_once_with(str(sample_clip))


@pytest.mark.asyncio
async def test_handle_upload_raises_on_missing_path(manager):
    with pytest.raises(ValueError, match="missing path"):
        await manager.handle_upload_message({"event_id": 1})


@pytest.mark.asyncio
async def test_handle_upload_propagates_storage_error(manager, sample_clip):
    manager._backend.upload = AsyncMock(side_effect=StorageUploadError("disk full"))
    payload = {"path": str(sample_clip), "event_id": 1, "camera": "cam"}
    with pytest.raises(StorageUploadError, match="disk full"):
        await manager.handle_upload_message(payload)
