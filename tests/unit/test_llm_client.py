"""Kiểm tra LLMClient bằng Fake, không gọi mạng."""

from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from medgraph.config.settings import Settings
from medgraph.llm.base import LLMError, LLMOutputError
from medgraph.llm.cache import CachedLLMClient
from medgraph.llm.factory import create_llm_client
from medgraph.llm.providers.fake import FakeLLMClient
from medgraph.models.llm import LLMResponse


class ExampleOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alias: str


class OtherOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str


def _settings() -> Settings:
    return Settings(
        neo4j_uri="bolt://unused:7687",
        neo4j_user="test",
        neo4j_password="test",
        llm_provider="fake",
        _env_file=None,
    )


@pytest.mark.unit
def test_fake_client_returns_typed_response_without_network() -> None:
    client = FakeLLMClient(["hello"])
    response = client.complete("prompt", model_tier="small", temperature=0.0)

    assert response == LLMResponse(
        text="hello", model="fake-small", input_tokens=0, output_tokens=0, latency_ms=0
    )
    assert client.call_count == 1
    with pytest.raises(LLMError, match="no queued response"):
        client.complete("prompt", model_tier="large", temperature=0.0)


@pytest.mark.unit
def test_structured_response_validates_json_and_schema() -> None:
    client = FakeLLMClient(['{"alias":"thở dốc"}', '{"unknown":true}', "not json"])
    result = client.complete_structured(
        "prompt", ExampleOutput, model_tier="small", temperature=0.0
    )
    assert result.alias == "thở dốc"
    with pytest.raises(LLMOutputError):
        client.complete_structured("prompt", ExampleOutput, model_tier="small", temperature=0.0)
    with pytest.raises(LLMOutputError):
        client.complete_structured("prompt", ExampleOutput, model_tier="small", temperature=0.0)


@pytest.mark.unit
def test_factory_selects_fake_and_rejects_unknown_provider() -> None:
    settings = _settings()
    assert isinstance(create_llm_client(settings), FakeLLMClient)
    invalid = settings.model_copy(update={"llm_provider": "unknown"})
    with pytest.raises(ValueError, match="Unsupported LLM_PROVIDER"):
        create_llm_client(invalid)


@pytest.mark.unit
def test_response_is_frozen_and_forbids_extra_fields() -> None:
    response = LLMResponse(
        text="ok", model="fake-small", input_tokens=0, output_tokens=0, latency_ms=0
    )
    with pytest.raises(ValidationError):
        response.text = "changed"
    with pytest.raises(ValidationError):
        LLMResponse(
            text="ok", model="fake-small", input_tokens=0, output_tokens=0, latency_ms=0, extra=1
        )


@pytest.mark.unit
def test_cache_reuses_complete_across_instances_and_separates_prompt_versions(
    tmp_path: Path,
) -> None:
    fake = FakeLLMClient(["v1", "v2"])
    first = CachedLLMClient(fake, tmp_path / "llm")
    kwargs = {
        "model_tier": "small",
        "temperature": 0.0,
        "prompt_name": "aliases",
        "prompt_version": "v1",
    }

    assert first.complete("prompt", **kwargs).text == "v1"
    second = CachedLLMClient(fake, tmp_path / "llm")
    assert second.complete("prompt", **kwargs).text == "v1"
    assert fake.call_count == 1
    assert second.complete("prompt", **{**kwargs, "prompt_version": "v2"}).text == "v2"
    assert fake.call_count == 2
    assert len(list((tmp_path / "llm").glob("*.json"))) == 2


@pytest.mark.unit
def test_cache_separates_schema_model_and_temperature(tmp_path: Path) -> None:
    fake = FakeLLMClient(['{"alias":"a"}', '{"name":"b"}', '{"alias":"c"}'])
    cached = CachedLLMClient(fake, tmp_path / "llm")

    assert (
        cached.complete_structured(
            "prompt", ExampleOutput, model_tier="small", temperature=0.0
        ).alias
        == "a"
    )
    assert (
        cached.complete_structured(
            "prompt", ExampleOutput, model_tier="small", temperature=0.0
        ).alias
        == "a"
    )
    assert (
        cached.complete_structured("prompt", OtherOutput, model_tier="small", temperature=0.0).name
        == "b"
    )
    assert (
        cached.complete_structured(
            "prompt", ExampleOutput, model_tier="large", temperature=0.5
        ).alias
        == "c"
    )
    assert fake.call_count == 3


@pytest.mark.unit
def test_invalid_cache_entry_is_replaced(tmp_path: Path) -> None:
    fake = FakeLLMClient(["first", "second"])
    cached = CachedLLMClient(fake, tmp_path / "llm")
    assert cached.complete("prompt", model_tier="small", temperature=0.0).text == "first"
    path = next((tmp_path / "llm").glob("*.json"))
    path.write_text("bad json", encoding="utf-8")
    assert cached.complete("prompt", model_tier="small", temperature=0.0).text == "second"
    assert fake.call_count == 2


@pytest.mark.unit
def test_cache_key_includes_provider_and_prompt_name(tmp_path: Path) -> None:
    class AlternateFake(FakeLLMClient):
        @property
        def provider(self) -> str:
            return "alternate-fake"

    first = FakeLLMClient(["first", "renamed"])
    alternate = AlternateFake(["alternate"])
    cache_dir = tmp_path / "llm"

    assert (
        CachedLLMClient(first, cache_dir)
        .complete("prompt", model_tier="small", temperature=0.0, prompt_name="one")
        .text
        == "first"
    )
    assert (
        CachedLLMClient(alternate, cache_dir)
        .complete("prompt", model_tier="small", temperature=0.0, prompt_name="one")
        .text
        == "alternate"
    )
    assert (
        CachedLLMClient(first, cache_dir)
        .complete("prompt", model_tier="small", temperature=0.0, prompt_name="two")
        .text
        == "renamed"
    )
    assert len(list(cache_dir.glob("*.json"))) == 3
