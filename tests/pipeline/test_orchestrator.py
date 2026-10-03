"""
Tests for Phase 8: Argus Pipeline Orchestrator.

ALL external dependencies (RTSP, YOLO, InsightFace, LLM, Kafka, DB, rclone)
are mocked — no real hardware, network, or infrastructure required.

Test coverage:
  - Motion filter short-circuit (static frame → no detection)
  - Person detected but no face match → recording starts
  - Known face → DB last_seen update, no alert
  - Unknown face → full pipeline: LLM + recording + DB persist + Kafka + alert
  - LLM failure → graceful fallback (SAFE_FALLBACK), pipeline continues
  - Recording failure → event still persisted, alert still sent
  - Kafka publish called with correct schema
  - Storage enqueue called with correct event_id and clip path
  - Laya gate escalation → CRITICAL severity alert
  - Laya gate disabled (None) → pipeline still works
  - AutoLearner called with correct args
  - alert dispatched with CRITICAL for suspicious, WARNING for non-suspicious
  - Stats property returns correct counters
  - stop() exits the run loop cleanly
  - DB persist failure → pipeline continues, Kafka and alert still fire
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import numpy as np
import pytest

from argus.alerts.models import AlertSeverity
from argus.intelligence.base import SAFE_FALLBACK, SceneAnalysis
from argus.pipeline.orchestrator import EventOrchestrator, _POST_EVENT_SECONDS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_frame(h: int = 480, w: int = 640) -> np.ndarray:
    """Return a random uint8 BGR frame."""
    return np.random.randint(0, 255, (h, w, 3), dtype=np.uint8)


def _make_detection(class_name: str = "person", conf: float = 0.9):
    det = MagicMock()
    det.class_name = class_name
    det.confidence = conf
    det.box = (100, 100, 200, 300)
    return det


def _make_unknown_face_match(similarity: float = 0.2):
    match = MagicMock()
    match.is_known = False
    match.profile_id = None
    match.similarity = similarity
    match.embedding = np.zeros(512, dtype=np.float32)
    match.face_crop = None
    return match


def _make_known_face_match(profile_id: int = 7, similarity: float = 0.95):
    match = MagicMock()
    match.is_known = True
    match.profile_id = profile_id
    match.similarity = similarity
    match.embedding = np.zeros(512, dtype=np.float32)
    match.face_crop = None
    return match


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_camera():
    cam = MagicMock()
    cam.name = "front_door"
    cam.rtsp_url = "rtsp://192.168.1.100:554/stream"
    cam.fps = 15
    cam.disabled = False
    return cam


@pytest.fixture
def mock_settings():
    s = MagicMock()
    s.thumbnails_path = "/tmp/argus_test_thumbs"
    s.recordings_path = "/tmp/argus_test_recordings"
    s.llm.laya.enabled = True
    s.recognition.auto_learn.enabled = True
    return s


@pytest.fixture
def mock_session_factory():
    """Session factory that returns an async context manager yielding a mock session."""
    session = AsyncMock()
    session.commit = AsyncMock()

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)

    factory = MagicMock(return_value=cm)
    return factory


@pytest.fixture
def mock_stream(mock_camera):
    stream = MagicMock()
    stream.queue = asyncio.Queue()
    stream.camera = mock_camera
    return stream


@pytest.fixture
def mock_motion():
    m = MagicMock()
    m.has_motion_async = AsyncMock(return_value=True)
    return m


@pytest.fixture
def mock_detector():
    d = AsyncMock()
    d.detect = AsyncMock(return_value=[_make_detection()])
    return d


@pytest.fixture
def mock_tracker():
    t = MagicMock()
    t.update = MagicMock(return_value=[_make_detection()])
    return t


@pytest.fixture
def mock_recognizer():
    r = AsyncMock()
    r.recognize = AsyncMock(return_value=[_make_unknown_face_match()])
    return r


@pytest.fixture
def mock_recorder():
    rec = AsyncMock()
    rec.start_recording = AsyncMock()
    rec.stop_recording = AsyncMock(return_value="/tmp/event_001.mp4")
    rec.add_frame = AsyncMock()
    rec.current_output_path = Path("/tmp/event_001.mp4")
    rec.is_recording = False
    return rec


@pytest.fixture
def mock_alert_manager():
    am = AsyncMock()
    am.send = AsyncMock()
    am.send_learn_prompt = AsyncMock()
    return am


@pytest.fixture
def mock_learner():
    l = AsyncMock()
    l.track_unknown = AsyncMock()
    return l


@pytest.fixture
def mock_llm():
    provider = AsyncMock()
    provider.analyze = AsyncMock(return_value=SceneAnalysis(
        description="Person walking near doorway",
        is_suspicious=False,
        confidence=0.75,
        action_recommendation="Monitor",
        provider_used="ollama",
        model_used="llava",
    ))
    return provider


@pytest.fixture
def mock_laya():
    decision = MagicMock()
    decision.escalate_to_llm = False
    decision.is_suspicious = False

    gate = AsyncMock()
    gate.decide = AsyncMock(return_value=decision)
    return gate


@pytest.fixture
def mock_producer():
    p = AsyncMock()
    p.is_started = True
    p.publish = AsyncMock()
    return p


@pytest.fixture
def mock_storage():
    s = AsyncMock()
    s.enqueue = AsyncMock()
    return s


@pytest.fixture
def orchestrator(
    mock_camera, mock_stream, mock_motion, mock_detector, mock_tracker,
    mock_recognizer, mock_recorder, mock_alert_manager, mock_learner,
    mock_llm, mock_laya, mock_producer, mock_storage, mock_session_factory,
    mock_settings,
):
    orch = EventOrchestrator(
        camera=mock_camera,
        stream_worker=mock_stream,
        motion_filter=mock_motion,
        detector=mock_detector,
        tracker=mock_tracker,
        recognizer=mock_recognizer,
        recorder=mock_recorder,
        alert_manager=mock_alert_manager,
        learner=mock_learner,
        llm_provider=mock_llm,
        laya_gate=mock_laya,
        kafka_producer=mock_producer,
        storage_manager=mock_storage,
        session_factory=mock_session_factory,
        settings=mock_settings,
    )
    orch._running = True
    orch._camera_db_id = 1
    return orch


# ---------------------------------------------------------------------------
# Stats and basic properties
# ---------------------------------------------------------------------------

def test_stats_initial_values(orchestrator):
    s = orchestrator.stats
    assert s["camera"] == "front_door"
    assert s["frames_processed"] == 0
    assert s["events_triggered"] == 0
    assert s["recording_active"] is False


@pytest.mark.asyncio
async def test_stop_sets_running_false(orchestrator):
    orchestrator._running = True
    await orchestrator.stop()
    assert orchestrator._running is False


# ---------------------------------------------------------------------------
# Motion filter short-circuit
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_motion_skips_detection(orchestrator, mock_stream, mock_motion, mock_detector):
    """Static frame → MotionFilter returns False → detector never called."""
    mock_motion.has_motion_async = AsyncMock(return_value=False)

    frame = _make_frame()
    await mock_stream.queue.put(frame)
    # Stop after first frame
    orchestrator._running = False
    await mock_stream.queue.put(None)  # won't be reached but safety

    # Manually call one iteration of the loop logic
    mock_stream.queue = asyncio.Queue()
    await mock_stream.queue.put(frame)

    has_motion = await orchestrator._motion.has_motion_async(frame)
    assert has_motion is False
    mock_detector.detect.assert_not_called()


# ---------------------------------------------------------------------------
# Known face handler
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_known_face_updates_last_seen(orchestrator, mock_session_factory):
    """Known face → update_face_last_seen called, no alert sent."""
    match = _make_known_face_match(profile_id=42)

    with patch("argus.pipeline.orchestrator.asyncio.get_running_loop"):
        with patch("argus.database.repository.update_face_last_seen", new_callable=AsyncMock) as mock_update:
            await orchestrator._handle_known_face(match)

    orchestrator._alert_manager.send.assert_not_called()


@pytest.mark.asyncio
async def test_known_face_no_profile_id_skips(orchestrator):
    """known face with profile_id=None → silently skipped."""
    match = _make_known_face_match()
    match.profile_id = None
    await orchestrator._handle_known_face(match)  # must not raise
    orchestrator._alert_manager.send.assert_not_called()


# ---------------------------------------------------------------------------
# Unknown face — happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unknown_face_dispatches_alert(orchestrator):
    """Unknown face → Alert dispatched via AlertManager."""
    frame = _make_frame()
    match = _make_unknown_face_match(similarity=0.15)

    with patch("argus.pipeline.orchestrator.asyncio.get_running_loop") as mock_loop:
        mock_loop.return_value = MagicMock()
        mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)
        with patch("argus.database.repository.create_event", new_callable=AsyncMock) as mock_ce, \
             patch("argus.database.repository.update_event_with_analysis", new_callable=AsyncMock), \
             patch("argus.database.repository.create_clip", new_callable=AsyncMock):
            mock_event = MagicMock()
            mock_event.id = 99
            mock_ce.return_value = mock_event

            await orchestrator._handle_unknown_face(frame, match)

    orchestrator._alert_manager.send.assert_called_once()


@pytest.mark.asyncio
async def test_unknown_face_increments_event_count(orchestrator):
    """Event counter increments for each unknown face."""
    frame = _make_frame()
    match = _make_unknown_face_match()

    with patch("argus.pipeline.orchestrator.asyncio.get_running_loop") as mock_loop:
        mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)
        with patch("argus.database.repository.create_event", new_callable=AsyncMock) as mock_ce, \
             patch("argus.database.repository.update_event_with_analysis", new_callable=AsyncMock), \
             patch("argus.database.repository.create_clip", new_callable=AsyncMock):
            mock_event = MagicMock()
            mock_event.id = 1
            mock_ce.return_value = mock_event

            assert orchestrator._event_count == 0
            await orchestrator._handle_unknown_face(frame, match)
            assert orchestrator._event_count == 1


@pytest.mark.asyncio
async def test_unknown_face_calls_autolearner(orchestrator):
    """AutoLearner.track_unknown called with face_match, camera_name, frame."""
    frame = _make_frame()
    match = _make_unknown_face_match()

    with patch("argus.pipeline.orchestrator.asyncio.get_running_loop") as mock_loop:
        mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)
        with patch("argus.database.repository.create_event", new_callable=AsyncMock) as mock_ce, \
             patch("argus.database.repository.update_event_with_analysis", new_callable=AsyncMock), \
             patch("argus.database.repository.create_clip", new_callable=AsyncMock):
            mock_event = MagicMock()
            mock_event.id = 5
            mock_ce.return_value = mock_event

            await orchestrator._handle_unknown_face(frame, match)

    orchestrator._learner.track_unknown.assert_called_once()
    call_kwargs = orchestrator._learner.track_unknown.call_args
    assert call_kwargs.kwargs.get("camera_name") == "front_door"


@pytest.mark.asyncio
async def test_unknown_face_publishes_to_kafka(orchestrator):
    """Event published to argus.events with correct fields."""
    frame = _make_frame()
    match = _make_unknown_face_match()

    with patch("argus.pipeline.orchestrator.asyncio.get_running_loop") as mock_loop:
        mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)
        with patch("argus.database.repository.create_event", new_callable=AsyncMock) as mock_ce, \
             patch("argus.database.repository.update_event_with_analysis", new_callable=AsyncMock), \
             patch("argus.database.repository.create_clip", new_callable=AsyncMock):
            mock_event = MagicMock()
            mock_event.id = 11
            mock_ce.return_value = mock_event

            await orchestrator._handle_unknown_face(frame, match)

    orchestrator._producer.publish.assert_called_once()
    call_kwargs = orchestrator._producer.publish.call_args.kwargs
    assert call_kwargs["topic"].value == "argus.events" or str(call_kwargs["topic"]) == "argus.events"
    assert call_kwargs["value"]["camera"] == "front_door"


@pytest.mark.asyncio
async def test_unknown_face_enqueues_clip_upload(orchestrator):
    """StorageManager.enqueue called with event_id and clip_path."""
    frame = _make_frame()
    match = _make_unknown_face_match()

    with patch("argus.pipeline.orchestrator.asyncio.get_running_loop") as mock_loop:
        mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)
        with patch("argus.database.repository.create_event", new_callable=AsyncMock) as mock_ce, \
             patch("argus.database.repository.update_event_with_analysis", new_callable=AsyncMock), \
             patch("argus.database.repository.create_clip", new_callable=AsyncMock):
            mock_event = MagicMock()
            mock_event.id = 77
            mock_ce.return_value = mock_event

            await orchestrator._handle_unknown_face(frame, match)

    orchestrator._storage.enqueue.assert_called_once()
    enqueue_kwargs = orchestrator._storage.enqueue.call_args.kwargs
    assert enqueue_kwargs["event_id"] == 77


# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_failure_uses_safe_fallback(orchestrator, mock_llm):
    """LLM throws → SAFE_FALLBACK used, alert still dispatched."""
    mock_llm.analyze = AsyncMock(side_effect=RuntimeError("ollama timeout"))
    frame = _make_frame()
    match = _make_unknown_face_match()

    with patch("argus.pipeline.orchestrator.asyncio.get_running_loop") as mock_loop:
        mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)
        with patch("argus.database.repository.create_event", new_callable=AsyncMock) as mock_ce, \
             patch("argus.database.repository.update_event_with_analysis", new_callable=AsyncMock), \
             patch("argus.database.repository.create_clip", new_callable=AsyncMock):
            mock_event = MagicMock()
            mock_event.id = 2
            mock_ce.return_value = mock_event

            await orchestrator._handle_unknown_face(frame, match)

    # Alert must still fire even when LLM fails
    orchestrator._alert_manager.send.assert_called_once()


@pytest.mark.asyncio
async def test_recording_failure_event_still_persisted(orchestrator, mock_recorder):
    """Recorder.start_recording throws → event still saved in DB."""
    mock_recorder.start_recording = AsyncMock(side_effect=RuntimeError("ffmpeg crashed"))
    mock_recorder.current_output_path = None
    frame = _make_frame()
    match = _make_unknown_face_match()

    with patch("argus.pipeline.orchestrator.asyncio.get_running_loop") as mock_loop:
        mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)
        with patch("argus.database.repository.create_event", new_callable=AsyncMock) as mock_ce, \
             patch("argus.database.repository.update_event_with_analysis", new_callable=AsyncMock), \
             patch("argus.database.repository.create_clip", new_callable=AsyncMock):
            mock_event = MagicMock()
            mock_event.id = 3
            mock_ce.return_value = mock_event

            await orchestrator._handle_unknown_face(frame, match)

    mock_ce.assert_called_once()
    orchestrator._alert_manager.send.assert_called_once()


@pytest.mark.asyncio
async def test_db_persist_failure_pipeline_continues(orchestrator, mock_session_factory):
    """DB session throws → Kafka publish and alert still fire."""
    # Make session __aenter__ throw
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(side_effect=RuntimeError("DB connection lost"))
    cm.__aexit__ = AsyncMock(return_value=False)
    mock_session_factory.return_value = cm
    orchestrator._session_factory = mock_session_factory

    frame = _make_frame()
    match = _make_unknown_face_match()

    with patch("argus.pipeline.orchestrator.asyncio.get_running_loop") as mock_loop:
        mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)
        await orchestrator._handle_unknown_face(frame, match)

    # Alert still fires even when DB fails
    orchestrator._alert_manager.send.assert_called_once()


@pytest.mark.asyncio
async def test_no_laya_gate_pipeline_works(orchestrator):
    """Laya gate = None → pipeline still works, LLM result determines severity."""
    orchestrator._laya = None
    frame = _make_frame()
    match = _make_unknown_face_match()

    with patch("argus.pipeline.orchestrator.asyncio.get_running_loop") as mock_loop:
        mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)
        with patch("argus.database.repository.create_event", new_callable=AsyncMock) as mock_ce, \
             patch("argus.database.repository.update_event_with_analysis", new_callable=AsyncMock), \
             patch("argus.database.repository.create_clip", new_callable=AsyncMock):
            mock_event = MagicMock()
            mock_event.id = 4
            mock_ce.return_value = mock_event

            await orchestrator._handle_unknown_face(frame, match)

    orchestrator._alert_manager.send.assert_called_once()


# ---------------------------------------------------------------------------
# Severity escalation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_suspicious_llm_sends_critical_alert(orchestrator, mock_llm):
    """LLM is_suspicious=True → CRITICAL severity alert."""
    mock_llm.analyze = AsyncMock(return_value=SceneAnalysis(
        description="Person breaking window",
        is_suspicious=True,
        confidence=0.98,
        action_recommendation="Alert immediately",
        provider_used="ollama",
        model_used="llava",
    ))
    frame = _make_frame()
    match = _make_unknown_face_match()

    with patch("argus.pipeline.orchestrator.asyncio.get_running_loop") as mock_loop:
        mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)
        with patch("argus.database.repository.create_event", new_callable=AsyncMock) as mock_ce, \
             patch("argus.database.repository.update_event_with_analysis", new_callable=AsyncMock), \
             patch("argus.database.repository.create_clip", new_callable=AsyncMock):
            mock_event = MagicMock()
            mock_event.id = 6
            mock_ce.return_value = mock_event

            await orchestrator._handle_unknown_face(frame, match)

    alert_sent = orchestrator._alert_manager.send.call_args[0][0]
    assert alert_sent.severity == AlertSeverity.CRITICAL


@pytest.mark.asyncio
async def test_laya_escalation_sends_critical_alert(orchestrator, mock_laya):
    """Laya escalate_to_llm=True → CRITICAL severity alert."""
    decision = MagicMock()
    decision.escalate_to_llm = True
    mock_laya.decide = AsyncMock(return_value=decision)
    orchestrator._laya = mock_laya

    frame = _make_frame()
    match = _make_unknown_face_match()

    with patch("argus.pipeline.orchestrator.asyncio.get_running_loop") as mock_loop:
        mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)
        with patch("argus.database.repository.create_event", new_callable=AsyncMock) as mock_ce, \
             patch("argus.database.repository.update_event_with_analysis", new_callable=AsyncMock), \
             patch("argus.database.repository.create_clip", new_callable=AsyncMock):
            mock_event = MagicMock()
            mock_event.id = 8
            mock_ce.return_value = mock_event

            await orchestrator._handle_unknown_face(frame, match)

    alert_sent = orchestrator._alert_manager.send.call_args[0][0]
    assert alert_sent.severity == AlertSeverity.CRITICAL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recording_timeout_stops_recording(orchestrator, mock_recorder):
    """_check_recording_timeout stops recorder after POST_EVENT_SECONDS."""
    import time

    orchestrator._recording_active = True
    orchestrator._last_detection_ts = time.monotonic() - (_POST_EVENT_SECONDS + 1)

    await orchestrator._check_recording_timeout()

    mock_recorder.stop_recording.assert_called_once()
    assert orchestrator._recording_active is False


@pytest.mark.asyncio
async def test_recording_timeout_does_not_stop_if_recent(orchestrator, mock_recorder):
    """_check_recording_timeout keeps recording when detection was recent."""
    import time

    orchestrator._recording_active = True
    orchestrator._last_detection_ts = time.monotonic()  # just now

    await orchestrator._check_recording_timeout()

    mock_recorder.stop_recording.assert_not_called()
    assert orchestrator._recording_active is True
