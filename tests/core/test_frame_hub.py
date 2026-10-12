"""
Unit tests for Argus FrameHub live video distribution bus and RTSP prober.
"""
from __future__ import annotations

import asyncio
import numpy as np
import pytest

from argus.core.frame_hub import FrameHub


@pytest.fixture
def hub():
    return FrameHub()


@pytest.mark.asyncio
async def test_frame_hub_placeholder_generation(hub):
    buf = hub.generate_placeholder_frame("Camera offline")
    assert isinstance(buf, bytes)
    assert len(buf) > 1000
    assert buf.startswith(b"\xff\xd8")  # Valid JPEG SOI marker


@pytest.mark.asyncio
async def test_frame_hub_publish_and_get(hub):
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    hub.publish_frame("test_cam", frame)

    jpeg = hub.get_latest_jpeg("test_cam")
    assert jpeg is not None
    assert isinstance(jpeg, bytes)
    assert jpeg.startswith(b"\xff\xd8")


@pytest.mark.asyncio
async def test_frame_hub_subscribe_receives_frames(hub):
    gen = hub.subscribe("test_cam")

    # First chunk is initial placeholder or cached frame
    first_chunk = await gen.__anext__()
    assert b"--frame\r\n" in first_chunk

    # Publish a real frame
    test_frame = np.ones((100, 100, 3), dtype=np.uint8) * 128
    hub.publish_frame("test_cam", test_frame)

    # Next chunk should be the published frame
    second_chunk = await gen.__anext__()
    assert b"--frame\r\n" in second_chunk
    assert b"Content-Type: image/jpeg\r\n\r\n" in second_chunk

    # Clean close generator
    await gen.aclose()
    assert not hub.has_subscribers("test_cam")


@pytest.mark.asyncio
async def test_frame_hub_probe_invalid_url(hub):
    res = await hub.probe_rtsp("not_a_valid_url")
    assert res["success"] is False
    assert "Invalid RTSP URL" in res["message"]


@pytest.mark.asyncio
async def test_frame_hub_probe_unreachable_host(hub):
    res = await hub.probe_rtsp("rtsp://192.0.2.1:554/live", timeout_seconds=1.0)
    assert res["success"] is False
    assert "unreachable" in res["message"].lower() or "timed out" in res["message"].lower()
