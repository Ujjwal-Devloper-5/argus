"""
Laya Decision Gate — Ultra-fast 33ms "System 1" suspicion classifier.

Laya is a 421M parameter non-autoregressive decision model by Convai Innovations,
built on ModernBERT-large. Unlike LLMs, it does NOT generate text. It answers
structured boolean/choice/score questions with calibrated probabilities in a
single forward pass.

Role in Argus Pipeline:
    Motion → YOLO → Face Recognition
        → Laya (33ms): "Is this suspicious?"
            → YES → Full LLM vision analysis (Ollama/GPT-4o etc.)
            → NO  → Log only, skip expensive LLM call (~80% cost reduction)

This makes Argus a two-brain system:
    - System 1 (Laya):  Fast, cheap, always-on reflex layer
    - System 2 (LLM):   Slow, expensive, deep reasoning layer

References:
    https://huggingface.co/convaiinnovations/laya
    https://huggingface.co/convaiinnovations/laya-typed-decisions
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class LayaDecision:
    """Result from the Laya decision gate."""

    is_suspicious: bool
    confidence: float          # Calibrated probability 0.0 - 1.0
    escalate_to_llm: bool      # Whether to run the full LLM analysis
    reasoning: str             # Human-readable explanation
    latency_ms: float          # Inference time in milliseconds


class LayaDecisionGate:
    """
    Fast "System 1" decision gate using the Laya 421M model.

    Answers the core question: "Should this detection be escalated
    to the expensive full LLM vision analysis?"

    Questions asked to Laya per detection:
        1. noul: "Is the person behaving suspiciously?"
        2. choice: "What is the activity level?" [loitering, passing, working, unknown]
        3. score: "How urgently should this be reviewed?" (0-10)

    All three answers are combined into a single escalation decision.
    """

    MODEL_ID = "convaiinnovations/laya-typed-decisions"

    def __init__(
        self,
        model_id: str = MODEL_ID,
        suspicion_threshold: float = 0.60,
        urgency_threshold: float = 6.0,
        device: str = "auto",
    ) -> None:
        self._model_id = model_id
        self._suspicion_threshold = suspicion_threshold
        self._urgency_threshold = urgency_threshold
        self._device = device
        self._agent: Any = None  # Loaded lazily on first use
        self._lock = asyncio.Lock()

    def _load_model(self) -> Any:
        """Load Laya model. Called once, cached in self._agent."""
        try:
            import laya  # type: ignore[import]
            agent = laya.load(self._model_id)
            logger.info("Laya decision model loaded", model=self._model_id)
            return agent
        except ImportError:
            logger.warning(
                "laya package not installed. Run: pip install laya. "
                "Falling back to heuristic decision gate."
            )
            return None
        except Exception as e:
            logger.warning("Failed to load Laya model", model=self._model_id, error=str(e))
            return None

    async def _ensure_loaded(self) -> None:
        """Lazily load model on first use (thread-safe)."""
        async with self._lock:
            if self._agent is None:
                loop = asyncio.get_event_loop()
                self._agent = await loop.run_in_executor(None, self._load_model)

    def _build_state(
        self,
        description: str,
        camera_name: str,
        time_of_day: str,
        face_is_known: bool,
        similarity_score: float,
        detection_confidence: float,
    ) -> str:
        """
        Build the Laya 'state' string from detection context.
        Laya reads this as its input for decision-making.
        """
        known_str = "known person" if face_is_known else "unknown person"
        return (
            f"Security camera '{camera_name}' detected {known_str} at {time_of_day}. "
            f"Scene description: {description}. "
            f"Face recognition similarity: {similarity_score:.2f}. "
            f"Detection confidence: {detection_confidence:.2f}."
        )

    def _heuristic_decision(
        self,
        face_is_known: bool,
        similarity_score: float,
        detection_confidence: float,
        time_of_day_hour: int,
    ) -> LayaDecision:
        """
        Fallback heuristic when Laya model is unavailable.
        Simple rules-based "System 1" — still much faster than running LLM.
        """
        import time
        is_night = time_of_day_hour >= 22 or time_of_day_hour <= 5
        is_unknown = not face_is_known
        high_confidence = detection_confidence >= 0.80

        suspicious = (is_unknown and is_night) or (is_unknown and high_confidence)
        confidence = 0.75 if suspicious else 0.30
        escalate = suspicious or (is_unknown and high_confidence)

        reasons = []
        if is_night:
            reasons.append("late-night detection")
        if is_unknown:
            reasons.append("unknown person")
        if high_confidence:
            reasons.append("high detection confidence")

        return LayaDecision(
            is_suspicious=suspicious,
            confidence=confidence,
            escalate_to_llm=escalate,
            reasoning=f"Heuristic: {', '.join(reasons) if reasons else 'normal activity'}",
            latency_ms=0.1,
        )

    async def decide(
        self,
        description: str,
        camera_name: str,
        face_is_known: bool,
        similarity_score: float = 0.0,
        detection_confidence: float = 0.9,
        time_of_day_hour: int | None = None,
    ) -> LayaDecision:
        """
        Run the Laya decision gate. Returns a LayaDecision in ~33ms.

        Args:
            description:         Scene description string (from motion/YOLO context)
            camera_name:         Camera identifier for context
            face_is_known:       Whether InsightFace matched a known profile
            similarity_score:    Face similarity score (0-1)
            detection_confidence: YOLO confidence score (0-1)
            time_of_day_hour:    Hour of day (0-23) for temporal context

        Returns:
            LayaDecision with escalate_to_llm flag.
        """
        import time as _time

        if time_of_day_hour is None:
            from datetime import datetime
            time_of_day_hour = datetime.now().hour

        time_str = f"{time_of_day_hour:02d}:00"

        await self._ensure_loaded()

        # If model failed to load, use heuristic fallback
        if self._agent is None:
            return self._heuristic_decision(
                face_is_known, similarity_score, detection_confidence, time_of_day_hour
            )

        state = self._build_state(
            description=description,
            camera_name=camera_name,
            time_of_day=time_str,
            face_is_known=face_is_known,
            similarity_score=similarity_score,
            detection_confidence=detection_confidence,
        )

        questions = [
            {
                "type": "noul",
                "text": "Is the person behaving suspiciously or in an unusual manner?",
                "key": "suspicious",
            },
            {
                "type": "choice",
                "text": "What best describes the person's activity?",
                "choices": ["loitering", "passing_through", "working", "unknown"],
                "key": "activity",
            },
            {
                "type": "score",
                "text": "How urgently should a security officer review this detection?",
                "min": 0,
                "max": 10,
                "key": "urgency",
            },
        ]

        try:
            t0 = _time.perf_counter()
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, lambda: self._agent.predict(state, questions=questions)
            )
            latency_ms = (_time.perf_counter() - t0) * 1000

            # Parse Laya structured output
            suspicious_prob = float(result.get("suspicious", {}).get("probability", 0.5))
            activity = result.get("activity", {}).get("label", "unknown")
            urgency = float(result.get("urgency", {}).get("value", 5.0))

            is_suspicious = suspicious_prob >= self._suspicion_threshold
            escalate = is_suspicious or urgency >= self._urgency_threshold or (
                not face_is_known and urgency >= 4.0
            )

            reasoning = (
                f"Laya: suspicious={suspicious_prob:.2f}, "
                f"activity={activity}, urgency={urgency:.1f}/10"
            )

            logger.debug(
                "Laya decision",
                suspicious=is_suspicious,
                probability=suspicious_prob,
                activity=activity,
                urgency=urgency,
                escalate=escalate,
                latency_ms=round(latency_ms, 1),
                camera=camera_name,
            )

            return LayaDecision(
                is_suspicious=is_suspicious,
                confidence=suspicious_prob,
                escalate_to_llm=escalate,
                reasoning=reasoning,
                latency_ms=round(latency_ms, 1),
            )

        except Exception as e:
            logger.warning("Laya decision failed, using heuristic", error=str(e))
            return self._heuristic_decision(
                face_is_known, similarity_score, detection_confidence, time_of_day_hour
            )
