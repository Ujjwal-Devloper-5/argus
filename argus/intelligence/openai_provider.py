from __future__ import annotations
import httpx
import numpy as np
import structlog
from argus.intelligence.base import LLMProvider, SceneAnalysis, SAFE_FALLBACK, encode_frame_to_base64, SYSTEM_PROMPT

logger = structlog.get_logger(__name__)


class OpenAIProvider(LLMProvider):
    """OpenAI GPT-4o Vision provider. Any vision model configurable via settings."""

    BASE_URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self, api_key: str, model: str = "gpt-4o", timeout: int = 30) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    async def analyze(self, frame: np.ndarray, context: str = "") -> SceneAnalysis:
        try:
            b64 = encode_frame_to_base64(frame)
            user_content = [
                {"type": "text", "text": context or "Analyze this security camera frame."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "low"}},
            ]
            payload = {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                "response_format": {"type": "json_object"},
                "max_tokens": 256,
            }
            headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}

            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(self.BASE_URL, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            raw_text = data["choices"][0]["message"]["content"]
            return self._parse_response(raw_text, "openai", self._model)
        except httpx.TimeoutException:
            logger.warning("OpenAI request timed out", model=self._model)
            return SAFE_FALLBACK
        except Exception as e:
            logger.warning("OpenAI analyze failed", model=self._model, error=str(e))
            return SAFE_FALLBACK
