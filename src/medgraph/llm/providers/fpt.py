"""Adapter DeepSeek-V4-Flash qua FPT AI Factory Chat Completions API."""

import json
from time import perf_counter

import httpx
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential

from medgraph.config.settings import Settings
from medgraph.llm.base import (
    LLMError,
    LLMOutputError,
    ModelTier,
    StructuredModel,
    parse_structured_response,
)
from medgraph.models.llm import LLMResponse


def _is_retryable(error: BaseException) -> bool:
    if isinstance(error, httpx.TransportError):
        return True
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code in (408, 409, 429) or error.response.status_code >= 500
    return False


class FPTDeepSeekClient:
    """Gọi một model DeepSeek tại FPT cho cả hai model tier."""

    def __init__(self, settings: Settings) -> None:
        if settings.fpt_api_key is None or not settings.fpt_api_key.get_secret_value().strip():
            raise LLMError("FPT_API_KEY is required for fpt provider")
        self._settings = settings
        self._url = f"{settings.fpt_base_url.rstrip('/')}/chat/completions"

    @property
    def provider(self) -> str:
        return "fpt"

    def model_for_tier(self, model_tier: ModelTier) -> str:
        if model_tier not in ("small", "large"):
            raise ValueError(f"Unknown model tier: {model_tier}")
        return self._settings.fpt_model

    def complete(
        self,
        prompt: str,
        *,
        model_tier: ModelTier,
        temperature: float,
        prompt_name: str | None = None,
        prompt_version: str | None = None,
    ) -> LLMResponse:
        model = self.model_for_tier(model_tier)
        retryer = Retrying(
            stop=stop_after_attempt(self._settings.llm_retry_attempts),
            wait=wait_exponential(
                multiplier=1,
                min=self._settings.llm_retry_min_wait_seconds,
                max=self._settings.llm_retry_max_wait_seconds,
            ),
            retry=retry_if_exception(_is_retryable),
            reraise=True,
        )
        started = perf_counter()

        def send() -> httpx.Response:
            response = httpx.post(
                self._url,
                headers={
                    "Authorization": f"Bearer {self._settings.fpt_api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": self._settings.llm_max_tokens,
                    "temperature": temperature,
                },
                timeout=self._settings.llm_timeout_seconds,
            )
            response.raise_for_status()
            return response

        try:
            response = retryer(send)
        except httpx.HTTPError as exc:
            raise LLMError(f"FPT request failed: {type(exc).__name__}") from exc

        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content:
                raise LLMOutputError("FPT response contains no text")
            return LLMResponse(
                text=content,
                model=body["model"],
                input_tokens=body["usage"]["prompt_tokens"],
                output_tokens=body["usage"]["completion_tokens"],
                latency_ms=(perf_counter() - started) * 1000,
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMOutputError("FPT response has invalid chat completion format") from exc

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
        schema_text = json.dumps(schema.model_json_schema(), ensure_ascii=False, sort_keys=True)
        structured_prompt = f"{prompt}\n\nReturn only JSON matching this schema: {schema_text}"
        response = self.complete(
            structured_prompt,
            model_tier=model_tier,
            temperature=temperature,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
        )
        return parse_structured_response(response.text, schema)
