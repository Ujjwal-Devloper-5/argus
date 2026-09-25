from __future__ import annotations
import httpx
import numpy as np
import structlog
from argus.intelligence.base import LLMProvider, SceneAnalysis, SAFE_FALLBACK, encode_frame_to_base64, SYSTEM_PROMPT

logger = structlog.get_logger(__name__)


class AnthropicProvider(LLMProvider):
    """Anthropic Claude Vision provider. Any claude model configurable via settings."""

    BASE_URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-5", timeout: int = 30) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    async def analyze(self, frame: np.ndarray, context: str = "") -> SceneAnalysis:
        try:
            b64 = encode_frame_to_base64(frame)
            payload = {
                "model": self._model,
                "max_tokens": 256,
                "system": SYSTEM_PROMPT,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                        {"type": "text", "text": context or "Analyze this security camera frame."},
                    ],
                }],
            }
            headers = {
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(self.BASE_URL, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            raw_text = data["content"][0]["text"]
            return self._parse_response(raw_text, "anthropic", self._model)
        except httpx.TimeoutException:
            logger.warning("Anthropic request timed out", model=self._model)
            return SAFE_FALLBACK
        except Exception as e:
            logger.warning("Anthropic analyze failed", model=self._model, error=str(e))
            return SAFE_FALLBACK
