"""DeepSeek qua endpoint Anthropic-compatible chính thức."""

from medgraph.config.settings import Settings
from medgraph.llm.providers.anthropic import AnthropicMessagesClient


class DeepSeekClient(AnthropicMessagesClient):
    """Adapter DeepSeek Flash cho cả hai model tier của MedGraph."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            api_key=settings.deepseek_api_key,
            provider_name="deepseek",
            model_small=settings.deepseek_model,
            model_large=settings.deepseek_model,
            base_url=settings.deepseek_base_url,
        )
