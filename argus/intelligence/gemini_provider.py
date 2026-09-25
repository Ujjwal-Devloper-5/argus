from __future__ import annotations
import httpx
import numpy as np
import structlog
from argus.intelligence.base import LLMProvider, SceneAnalysis, SAFE_FALLBACK, encode_frame_to_base64, SYSTEM_PROMPT

logger = structlog.get_logger(__name__)


class GeminiProvider(LLMProvider):
    """Google Gemini Vision provider. Any gemini model configurable via settings."""

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash", timeout: int = 30) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    async def analyze(self, frame: np.ndarray, context: str = "") -> SceneAnalysis:
        try:
            b64 = encode_frame_to_base64(frame)
            url = self.BASE_URL.format(model=self._model)
            payload = {
                "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                "contents": [{"parts": [
                    {"inline_data": {"mime_type": "image/jpeg", "data": b64}},
                    {"text": context or "Analyze this security camera frame."},
                ]}],
                "generationConfig": {"response_mime_type": "application/json", "maxOutputTokens": 256},
            }
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=payload, params={"key": self._api_key})
                resp.raise_for_status()
                data = resp.json()
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
            return self._parse_response(raw_text, "gemini", self._model)
        except httpx.TimeoutException:
            logger.warning("Gemini request timed out", model=self._model)
            return SAFE_FALLBACK
        except Exception as e:
            logger.warning("Gemini analyze failed", model=self._model, error=str(e))
            return SAFE_FALLBACK
