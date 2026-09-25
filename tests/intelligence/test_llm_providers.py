"""
Tests for Phase 5: LLM providers, Laya decision gate, and AutoLearner.
All HTTP calls are mocked — no real API or model calls.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np
import pytest

from argus.intelligence.base import SceneAnalysis, SAFE_FALLBACK, encode_frame_to_base64
from argus.intelligence.disabled import DisabledProvider
from argus.intelligence.learner import compute_face_hash, score_face_quality


@pytest.fixture
def frame():
    return np.zeros((100, 100, 3), dtype=np.uint8)


@pytest.fixture
def valid_json():
    return '{"description": "Person walking", "is_suspicious": false, "confidence": 0.85, "action_recommendation": "Monitor"}'


# --- Shared utilities ---

def test_encode_frame_returns_nonempty_string(frame):
    b64 = encode_frame_to_base64(frame)
    assert isinstance(b64, str) and len(b64) > 0


def test_safe_fallback_not_suspicious():
    assert SAFE_FALLBACK.is_suspicious is False
    assert SAFE_FALLBACK.confidence == 0.0


# --- DisabledProvider ---

@pytest.mark.asyncio
async def test_disabled_returns_fallback(frame):
    result = await DisabledProvider().analyze(frame)
    assert isinstance(result, SceneAnalysis)
    assert not result.is_suspicious


# --- OllamaProvider ---

@pytest.mark.asyncio
async def test_ollama_parses_valid(frame, valid_json):
    from argus.intelligence.ollama import OllamaProvider
    provider = OllamaProvider(host="http://localhost:11434", model="llava")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": valid_json}
    mock_resp.raise_for_status = MagicMock()
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        result = await provider.analyze(frame)
    assert result.description == "Person walking"
    assert result.provider_used == "ollama"


@pytest.mark.asyncio
async def test_ollama_fallback_on_timeout(frame):
    import httpx
    from argus.intelligence.ollama import OllamaProvider
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=httpx.TimeoutException("x")):
        result = await OllamaProvider("http://localhost:11434", "llava").analyze(frame)
    assert not result.is_suspicious


@pytest.mark.asyncio
async def test_ollama_fallback_on_bad_json(frame):
    from argus.intelligence.ollama import OllamaProvider
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "NOT JSON"}
    mock_resp.raise_for_status = MagicMock()
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        result = await OllamaProvider("http://localhost:11434", "llava").analyze(frame)
    assert not result.is_suspicious


# --- OpenAI Provider ---

@pytest.mark.asyncio
async def test_openai_parses_valid(frame, valid_json):
    from argus.intelligence.openai_provider import OpenAIProvider
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": valid_json}}]}
    mock_resp.raise_for_status = MagicMock()
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        result = await OpenAIProvider("sk-test", "gpt-4o").analyze(frame)
    assert result.provider_used == "openai"
    assert result.model_used == "gpt-4o"


# --- Factory ---

def test_factory_creates_ollama():
    from argus.intelligence.factory import LLMProviderFactory
    from argus.intelligence.ollama import OllamaProvider
    cfg = MagicMock()
    cfg.provider = "ollama"
    cfg.ollama.host = "http://localhost:11434"
    cfg.ollama.model = "llava"
    cfg.ollama.timeout_seconds = 30
    assert isinstance(LLMProviderFactory.create(cfg), OllamaProvider)


def test_factory_creates_disabled():
    from argus.intelligence.factory import LLMProviderFactory
    from argus.intelligence.disabled import DisabledProvider
    cfg = MagicMock()
    cfg.provider = "disabled"
    assert isinstance(LLMProviderFactory.create(cfg), DisabledProvider)


def test_factory_raises_unknown():
    from argus.intelligence.factory import LLMProviderFactory
    cfg = MagicMock()
    cfg.provider = "nonexistent_model_xyz"
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        LLMProviderFactory.create(cfg)


# --- Laya Decision Gate ---

@pytest.mark.asyncio
async def test_laya_heuristic_unknown_night():
    """Without the laya package, heuristic should flag unknown person at 3am."""
    from argus.intelligence.laya import LayaDecisionGate
    gate = LayaDecisionGate()
    gate._agent = None  # Force heuristic path
    # Patch ensure_loaded to do nothing
    gate._lock = __import__('asyncio').Lock()
    # Directly call heuristic
    decision = gate._heuristic_decision(
        face_is_known=False,
        similarity_score=0.2,
        detection_confidence=0.9,
        time_of_day_hour=3,
    )
    assert decision.is_suspicious is True
    assert decision.escalate_to_llm is True


@pytest.mark.asyncio
async def test_laya_heuristic_known_daytime():
    from argus.intelligence.laya import LayaDecisionGate
    gate = LayaDecisionGate()
    decision = gate._heuristic_decision(
        face_is_known=True,
        similarity_score=0.95,
        detection_confidence=0.9,
        time_of_day_hour=14,
    )
    assert decision.is_suspicious is False


# --- AutoLearner utilities ---

def test_face_hash_stable():
    emb = np.random.rand(512).astype(np.float32)
    assert compute_face_hash(emb) == compute_face_hash(emb.copy())


def test_face_hash_different_for_different_embeddings():
    a = np.random.rand(512).astype(np.float32)
    b = np.random.rand(512).astype(np.float32)
    assert compute_face_hash(a) != compute_face_hash(b)


def test_quality_score_sharp_vs_flat():
    sharp = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
    flat = np.full((100, 100, 3), 128, dtype=np.uint8)
    assert score_face_quality(sharp) > score_face_quality(flat)


def test_quality_score_empty_returns_zero():
    assert score_face_quality(np.zeros((0, 0, 3), dtype=np.uint8)) == 0.0
