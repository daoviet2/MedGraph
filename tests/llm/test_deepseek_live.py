"""DeepSeek live smoke test; chỉ chạy thủ công với API key."""

import pytest

from medgraph.config.settings import get_settings
from medgraph.llm.providers.deepseek import DeepSeekClient

pytestmark = pytest.mark.llm


def test_deepseek_live_completion() -> None:
    settings = get_settings()
    if settings.deepseek_api_key is None:
        pytest.skip("Set DEEPSEEK_API_KEY to run live test")
    response = DeepSeekClient(settings).complete(
        "Reply with one short greeting.", model_tier="small", temperature=0.0
    )
    assert response.text
    assert response.model
