from __future__ import annotations
import httpx
import numpy as np
import structlog
from argus.intelligence.base import LLMProvider, SceneAnalysis, SAFE_FALLBACK, encode_frame_to_base64, SYSTEM_PROMPT

logger = structlog.get_logger(__name__)


class OllamaProvider(LLMProvider):
    """
    Ollama local LLM provider. Supports any vision model installed in Ollama.
    Configure via settings.llm.ollama.model (e.g. llava, moondream2, llama3.2-vision).
    """

    def __init__(self, host: str, model: str, timeout: int = 30) -> None:
        self._host = host.rstrip("/")
        self._model = model
        self._timeout = timeout

    async def analyze(self, frame: np.ndarray, context: str = "") -> SceneAnalysis:
        """Send frame to Ollama /api/generate endpoint. Never raises."""
        try:
            b64 = encode_frame_to_base64(frame)
            prompt = SYSTEM_PROMPT
            if context:
                prompt += f"\n\nAdditional context: {context}"

            payload = {
                "model": self._model,
                "prompt": prompt,
                "images": [b64],
                "stream": False,
                "format": "json",
            }

            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{self._host}/api/generate", json=payload)
                resp.raise_for_status()
                data = resp.json()

            raw_text = data.get("response", "{}")
            return self._parse_response(raw_text, "ollama", self._model)

        except httpx.TimeoutException:
            logger.warning("Ollama request timed out", model=self._model)
            return SAFE_FALLBACK
        except Exception as e:
            logger.warning("Ollama analyze failed", model=self._model, error=str(e))
            return SAFE_FALLBACK
