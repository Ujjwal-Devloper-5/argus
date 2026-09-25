from __future__ import annotations
import base64
from abc import ABC, abstractmethod
from typing import Any
import cv2
import numpy as np
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger(__name__)


class SceneAnalysis(BaseModel):
    description: str = "Analysis unavailable"
    is_suspicious: bool = False
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    action_recommendation: str = "Monitor"
    provider_used: str = "unknown"  # Which provider produced this
    model_used: str = "unknown"     # Which exact model


SAFE_FALLBACK = SceneAnalysis(
    description="Analysis unavailable",
    is_suspicious=False,
    confidence=0.0,
    action_recommendation="Monitor",
)


def encode_frame_to_base64(frame: np.ndarray, quality: int = 80) -> str:
    """Encode numpy BGR frame to base64 JPEG string. Shared by all providers."""
    _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return base64.b64encode(buffer.tobytes()).decode("utf-8")


SYSTEM_PROMPT = (
    "You are a security camera AI assistant. Analyze the provided image and describe what you see. "
    "You MUST respond ONLY with valid JSON matching exactly this schema, no other text:\n"
    '{"description": "one concise sentence describing what the person is doing", '
    '"is_suspicious": true or false, '
    '"confidence": a float between 0.0 and 1.0, '
    '"action_recommendation": "Alert immediately" or "Monitor" or "Ignore"}'
)


class LLMProvider(ABC):
    @abstractmethod
    async def analyze(self, frame: np.ndarray, context: str = "") -> SceneAnalysis:
        """Analyze a frame and return structured scene analysis. NEVER raises."""
        ...

    def _parse_response(self, raw_text: str, provider: str, model: str) -> SceneAnalysis:
        """Shared JSON parser. Returns safe fallback on any parse error."""
        import json
        try:
            # Strip markdown code blocks if present
            text = raw_text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text)
            return SceneAnalysis(
                description=data.get("description", "No description"),
                is_suspicious=bool(data.get("is_suspicious", False)),
                confidence=float(data.get("confidence", 0.5)),
                action_recommendation=data.get("action_recommendation", "Monitor"),
                provider_used=provider,
                model_used=model,
            )
        except Exception as e:
            logger.warning("Failed to parse LLM response", provider=provider, error=str(e), raw=raw_text[:200])
            return SAFE_FALLBACK.model_copy(update={"provider_used": provider, "model_used": model})
