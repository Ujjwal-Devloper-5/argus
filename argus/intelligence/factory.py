from __future__ import annotations
from argus.intelligence.base import LLMProvider
import structlog

logger = structlog.get_logger(__name__)


class LLMProviderFactory:
    """
    Creates the correct LLM provider based on settings.
    NO models are hardcoded. All model names come from settings.
    Add a new provider by registering it in REGISTRY.
    """

    @staticmethod
    def create(llm_config) -> LLMProvider:
        from argus.intelligence.ollama import OllamaProvider
        from argus.intelligence.openai_provider import OpenAIProvider
        from argus.intelligence.anthropic_provider import AnthropicProvider
        from argus.intelligence.gemini_provider import GeminiProvider
        from argus.intelligence.disabled import DisabledProvider

        provider_name = llm_config.provider

        REGISTRY = {
            "ollama": lambda: OllamaProvider(
                host=llm_config.ollama.host,
                model=llm_config.ollama.model,
                timeout=llm_config.ollama.timeout_seconds,
            ),
            "openai": lambda: OpenAIProvider(
                api_key=llm_config.openai.api_key.get_secret_value(),
                model=llm_config.openai.model,
                timeout=llm_config.openai.timeout_seconds,
            ),
            "anthropic": lambda: AnthropicProvider(
                api_key=llm_config.anthropic.api_key.get_secret_value(),
                model=llm_config.anthropic.model,
                timeout=llm_config.anthropic.timeout_seconds,
            ),
            "gemini": lambda: GeminiProvider(
                api_key=llm_config.gemini.api_key.get_secret_value(),
                model=llm_config.gemini.model,
                timeout=llm_config.gemini.timeout_seconds,
            ),
            "disabled": lambda: DisabledProvider(),
        }

        if provider_name not in REGISTRY:
            raise ValueError(
                f"Unknown LLM provider: '{provider_name}'. "
                f"Valid options: {list(REGISTRY.keys())}"
            )

        provider = REGISTRY[provider_name]()
        logger.info("LLM provider created", provider=provider_name)
        return provider

    @staticmethod
    def create_laya_gate(settings) -> "LayaDecisionGate":
        """Create the Laya fast decision gate. Separate from LLM providers."""
        from argus.intelligence.laya import LayaDecisionGate
        return LayaDecisionGate(
            model_id=settings.llm.laya.model_id,
            suspicion_threshold=settings.llm.laya.suspicion_threshold,
            urgency_threshold=settings.llm.laya.urgency_threshold,
        )
