"""Chọn LLM provider theo Settings."""

from medgraph.config.settings import Settings
from medgraph.llm.base import LLMClient
from medgraph.llm.providers.fake import FakeLLMClient


def create_llm_client(settings: Settings) -> LLMClient:
    if settings.llm_provider == "fake":
        return FakeLLMClient()
    if settings.llm_provider == "fpt":
        from medgraph.llm.providers.fpt import FPTDeepSeekClient

        return FPTDeepSeekClient(settings)
    raise ValueError(f"Unsupported LLM_PROVIDER: {settings.llm_provider}")
