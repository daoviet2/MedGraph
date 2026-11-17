"""Adapter Anthropic SDK sang hợp đồng LLMClient."""

import json
from time import perf_counter

from anthropic import (
    Anthropic,
    APIConnectionError,
    APIError,
    APIStatusError,
    InternalServerError,
    RateLimitError,
)
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
    return isinstance(error, (APIConnectionError, RateLimitError, InternalServerError)) or (
        isinstance(error, APIStatusError) and error.status_code in (408, 409)
    )


class AnthropicClient:
    """Bọc Anthropic SDK; tenacity quản lý retry, SDK retry được tắt."""

    def __init__(self, settings: Settings) -> None:
        api_key = settings.anthropic_api_key
        if api_key is None or not api_key.get_secret_value().strip():
            raise LLMError("ANTHROPIC_API_KEY is required for anthropic provider")
        self._settings = settings
        self._client = Anthropic(
            api_key=api_key.get_secret_value(),
            timeout=settings.llm_timeout_seconds,
            max_retries=0,
        )

    @property
    def provider(self) -> str:
        return "anthropic"

    def model_for_tier(self, model_tier: ModelTier) -> str:
        if model_tier == "small":
            return self._settings.llm_model_small
        if model_tier == "large":
            return self._settings.llm_model_large
        raise ValueError(f"Unknown model tier: {model_tier}")

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
        try:
            message = retryer(
                self._client.messages.create,
                model=model,
                max_tokens=self._settings.llm_max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
        except APIError as exc:
            raise LLMError(f"Anthropic request failed: {type(exc).__name__}") from exc

        text = "".join(block.text for block in message.content if block.type == "text")
        if not text:
            raise LLMOutputError("Anthropic response contains no text")
        return LLMResponse(
            text=text,
            model=message.model,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            latency_ms=(perf_counter() - started) * 1000,
        )

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
