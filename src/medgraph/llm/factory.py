"""Chọn LLM provider theo Settings."""

from medgraph.config.settings import Settings
from medgraph.llm.base import LLMClient
from medgraph.llm.providers.fake import FakeLLMClient


def create_llm_client(settings: Settings) -> LLMClient:
    if settings.llm_provider == "fake":
        return FakeLLMClient()
    if settings.llm_provider == "anthropic":
        from medgraph.llm.providers.anthropic import AnthropicClient

        return AnthropicClient(settings)
    if settings.llm_provider == "deepseek":
        from medgraph.llm.providers.deepseek import DeepSeekClient

        return DeepSeekClient(settings)
    raise ValueError(f"Unsupported LLM_PROVIDER: {settings.llm_provider}")
