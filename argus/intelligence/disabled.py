from __future__ import annotations
import numpy as np
from argus.intelligence.base import LLMProvider, SceneAnalysis, SAFE_FALLBACK


class DisabledProvider(LLMProvider):
    """No-op provider when LLM analysis is disabled. Always returns safe fallback."""

    async def analyze(self, frame: np.ndarray, context: str = "") -> SceneAnalysis:
        return SAFE_FALLBACK
