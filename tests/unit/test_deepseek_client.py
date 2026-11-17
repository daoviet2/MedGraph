"""Kiểm tra DeepSeek adapter bằng SDK giả, không gọi mạng."""

from types import SimpleNamespace

import pytest
from pydantic import BaseModel, SecretStr

from medgraph.config.settings import Settings
from medgraph.llm.base import LLMError, LLMOutputError
from medgraph.llm.factory import create_llm_client
from medgraph.llm.providers import anthropic as anthropic_provider
from medgraph.llm.providers.deepseek import DeepSeekClient


class ExampleResult(BaseModel):
    answer: str


def _settings(key: SecretStr | None) -> Settings:
    return Settings(
        neo4j_uri="bolt://unused:7687",
        neo4j_user="test",
        neo4j_password="test",
        llm_provider="deepseek",
        deepseek_api_key=key,
        _env_file=None,
    )


@pytest.mark.unit
def test_deepseek_uses_official_anthropic_compatible_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructed: list[object] = []

    class FakeMessages:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def create(self, **kwargs: object) -> object:
            self.calls.append(kwargs)
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="hello")],
                model=kwargs["model"],
                usage=SimpleNamespace(input_tokens=3, output_tokens=2),
            )

    class FakeSDK:
        def __init__(self, **kwargs: object) -> None:
            self.options = kwargs
            self.messages = FakeMessages()
            constructed.append(self)

    monkeypatch.setattr(anthropic_provider, "Anthropic", FakeSDK)
    client = create_llm_client(_settings(SecretStr("test-deepseek-key")))

    assert isinstance(client, DeepSeekClient)
    assert client.provider == "deepseek"
    assert client.model_for_tier("small") == "deepseek-flash"
    assert client.model_for_tier("large") == "deepseek-flash"
    assert constructed[0].options["base_url"] == "https://api.deepseek.com/anthropic"
    assert constructed[0].options["max_retries"] == 0

    response = client.complete("prompt", model_tier="small", temperature=0.0)
    assert response.text == "hello"
    assert response.model == "deepseek-flash"
    assert response.input_tokens == 3
    assert response.output_tokens == 2
    assert constructed[0].messages.calls[0]["model"] == "deepseek-flash"


@pytest.mark.unit
def test_deepseek_missing_key_raises_typed_error() -> None:
    with pytest.raises(LLMError, match="DEEPSEEK_API_KEY"):
        create_llm_client(_settings(None))


@pytest.mark.unit
def test_deepseek_structured_output_rejects_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeMessages:
        def create(self, **kwargs: object) -> object:
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text="not json")],
                model=kwargs["model"],
                usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            )

    class FakeSDK:
        def __init__(self, **kwargs: object) -> None:
            self.messages = FakeMessages()

    monkeypatch.setattr(anthropic_provider, "Anthropic", FakeSDK)
    client = DeepSeekClient(_settings(SecretStr("test-deepseek-key")))
    with pytest.raises(LLMOutputError):
        client.complete_structured("prompt", ExampleResult, model_tier="small", temperature=0.0)
