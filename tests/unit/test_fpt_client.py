"""Kiểm tra adapter FPT bằng HTTP giả, không gọi mạng."""

import httpx
import pytest
from pydantic import BaseModel, SecretStr

from medgraph.config.settings import Settings
from medgraph.llm.base import LLMError, LLMOutputError
from medgraph.llm.factory import create_llm_client
from medgraph.llm.providers.fpt import FPTDeepSeekClient


class ExampleResult(BaseModel):
    answer: str


def _settings(key: SecretStr | None, **overrides: object) -> Settings:
    return Settings(
        neo4j_uri="bolt://unused:7687",
        neo4j_user="test",
        neo4j_password="test",
        llm_provider="fpt",
        fpt_api_key=key,
        _env_file=None,
        **overrides,
    )


def _response(text: str = "hello") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "code": 200,
            "message": "Chat completion successful",
            "data": {
                "choices": [{"message": {"content": text}}],
                "model": "DeepSeek-V4-Flash",
                "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            },
        },
        request=httpx.Request("POST", "https://mkp-api.fptcloud.com/v1/chat/completions"),
    )


@pytest.mark.unit
def test_fpt_sends_deepseek_model_to_serverless_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def fake_post(client: httpx.Client, url: str, **kwargs: object) -> httpx.Response:
        calls.append((url, kwargs))
        return _response()

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    client = create_llm_client(_settings(SecretStr("test-fpt-key")))

    assert isinstance(client, FPTDeepSeekClient)
    assert client.provider == "fpt"
    assert client.model_for_tier("small") == "DeepSeek-V4-Flash"
    assert client.model_for_tier("large") == "DeepSeek-V4-Flash"

    response = client.complete("prompt", model_tier="small", temperature=0.0)
    assert response.text == "hello"
    assert response.model == "DeepSeek-V4-Flash"
    assert response.input_tokens == 3
    assert response.output_tokens == 2
    assert calls[0][0] == "https://mkp-api.fptcloud.com/v1/chat/completions"
    assert calls[0][1]["headers"]["Authorization"] == "Bearer test-fpt-key"
    assert calls[0][1]["json"]["model"] == "DeepSeek-V4-Flash"


@pytest.mark.unit
def test_fpt_missing_key_raises_typed_error() -> None:
    with pytest.raises(LLMError, match="FPT_API_KEY"):
        create_llm_client(_settings(None))


@pytest.mark.unit
def test_fpt_structured_output_rejects_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx.Client, "post", lambda *args, **kwargs: _response("not json"))
    client = FPTDeepSeekClient(_settings(SecretStr("test-fpt-key")))
    with pytest.raises(LLMOutputError):
        client.complete_structured("prompt", ExampleResult, model_tier="small", temperature=0.0)


@pytest.mark.unit
def test_fpt_retries_transient_http_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0

    def fake_post(*args: object, **kwargs: object) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, request=httpx.Request("POST", "https://token-api.fpt.ai/v1"))
        return _response()

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    client = FPTDeepSeekClient(
        _settings(
            SecretStr("test-fpt-key"),
            llm_retry_min_wait_seconds=0,
            llm_retry_max_wait_seconds=0,
        )
    )
    assert client.complete("prompt", model_tier="large", temperature=0).text == "hello"
    assert attempts == 2


@pytest.mark.unit
def test_fpt_rejects_bad_response_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        httpx.Client,
        "post",
        lambda *args, **kwargs: httpx.Response(
            200, json={"choices": []}, request=httpx.Request("POST", "https://token-api.fpt.ai/v1")
        ),
    )
    client = FPTDeepSeekClient(_settings(SecretStr("test-fpt-key")))
    with pytest.raises(LLMOutputError):
        client.complete("prompt", model_tier="small", temperature=0)


@pytest.mark.unit
def test_fpt_rejects_invalid_key_without_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0

    def fake_post(*args: object, **kwargs: object) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(401, request=httpx.Request("POST", "https://token-api.fpt.ai/v1"))

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    client = FPTDeepSeekClient(_settings(SecretStr("invalid-key")))
    with pytest.raises(LLMError, match="HTTPStatusError"):
        client.complete("prompt", model_tier="small", temperature=0)
    assert attempts == 1
