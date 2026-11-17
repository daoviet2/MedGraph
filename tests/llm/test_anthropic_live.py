"""Smoke test gọi Claude thật; chỉ chạy thủ công với marker llm."""

import pytest

from medgraph.config.settings import get_settings
from medgraph.llm.providers.anthropic import AnthropicClient

pytestmark = pytest.mark.llm


def test_anthropic_live_completion() -> None:
    settings = get_settings()
    if settings.anthropic_api_key is None:
        pytest.skip("Set ANTHROPIC_API_KEY and a valid LLM_MODEL_SMALL to run live test")
    response = AnthropicClient(settings).complete(
        "Reply with one short greeting.", model_tier="small", temperature=0.0
    )
    assert response.text
    assert response.model
