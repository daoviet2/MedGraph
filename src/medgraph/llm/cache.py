"""File cache decorator cho LLMClient."""

import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path

from pydantic import BaseModel, ValidationError

from medgraph.llm.base import LLMClient, ModelTier, StructuredModel
from medgraph.models.llm import LLMResponse

logger = logging.getLogger(__name__)


class CachedLLMClient:
    """Cache theo provider, model, prompt version, nhiệt độ và schema."""

    def __init__(self, client: LLMClient, cache_dir: Path = Path(".cache/llm")) -> None:
        self._client = client
        self._cache_dir = cache_dir

    @property
    def provider(self) -> str:
        return self._client.provider

    def model_for_tier(self, model_tier: ModelTier) -> str:
        return self._client.model_for_tier(model_tier)

    def _path(
        self,
        prompt: str,
        *,
        model_tier: ModelTier,
        temperature: float,
        prompt_name: str | None,
        prompt_version: str | None,
        schema: type[BaseModel] | None,
    ) -> Path:
        schema_identity = (
            {
                "name": f"{schema.__module__}.{schema.__qualname__}",
                "json_schema": schema.model_json_schema(),
            }
            if schema is not None
            else None
        )
        key = {
            "provider": self.provider,
            "model": self.model_for_tier(model_tier),
            "prompt_name": prompt_name,
            "prompt_version": prompt_version,
            "prompt_text": prompt,
            "temperature": temperature,
            "schema": schema_identity,
        }
        payload = json.dumps(key, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return self._cache_dir / f"{digest}.json"

    @staticmethod
    def _read(path: Path, schema: type[StructuredModel]) -> StructuredModel | None:
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return schema.model_validate(data["result"])
        except (OSError, json.JSONDecodeError, KeyError, ValidationError, TypeError) as exc:
            logger.warning("Ignoring invalid LLM cache entry %s: %s", path, exc)
            return None

    @staticmethod
    def _write(path: Path, value: BaseModel) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix="llm-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump({"result": value.model_dump(mode="json")}, stream, ensure_ascii=False)
            os.replace(temporary, path)
        except OSError:
            Path(temporary).unlink(missing_ok=True)
            raise

    def complete(
        self,
        prompt: str,
        *,
        model_tier: ModelTier,
        temperature: float,
        prompt_name: str | None = None,
        prompt_version: str | None = None,
    ) -> LLMResponse:
        path = self._path(
            prompt,
            model_tier=model_tier,
            temperature=temperature,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            schema=None,
        )
        cached = self._read(path, LLMResponse)
        if cached is not None:
            return cached
        response = self._client.complete(
            prompt,
            model_tier=model_tier,
            temperature=temperature,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
        )
        self._write(path, response)
        return response

    def complete_structured(
        self,
        prompt: str,
        schema: type[StructuredModel],
        *,
        model_tier: ModelTier,
        temperature: float,
        prompt_name: str | None = None,
        prompt_version: str | None = None,
    ) -> StructuredModel:
        path = self._path(
            prompt,
            model_tier=model_tier,
            temperature=temperature,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            schema=schema,
        )
        cached = self._read(path, schema)
        if cached is not None:
            return cached
        response = self._client.complete_structured(
            prompt,
            schema,
            model_tier=model_tier,
            temperature=temperature,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
        )
        self._write(path, response)
        return response
