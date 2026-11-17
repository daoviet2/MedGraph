"""LLM giả xác định trước phản hồi, không gọi mạng."""

from collections import deque
from collections.abc import Iterable

from medgraph.llm.base import (
    LLMError,
    ModelTier,
    StructuredModel,
    parse_structured_response,
)
from medgraph.models.llm import LLMResponse


class FakeLLMClient:
    def __init__(self, responses: Iterable[str] = ()) -> None:
        self._responses = deque(responses)
        self.call_count = 0

    @property
    def provider(self) -> str:
        return "fake"

    def model_for_tier(self, model_tier: ModelTier) -> str:
        if model_tier not in ("small", "large"):
            raise ValueError(f"Unknown model tier: {model_tier}")
        return f"fake-{model_tier}"

    def complete(
        self,
        prompt: str,
        *,
        model_tier: ModelTier,
        temperature: float,
        prompt_name: str | None = None,
        prompt_version: str | None = None,
    ) -> LLMResponse:
        self.call_count += 1
        if not self._responses:
            raise LLMError("FakeLLMClient has no queued response")
        return LLMResponse(
            text=self._responses.popleft(),
            model=self.model_for_tier(model_tier),
            input_tokens=0,
            output_tokens=0,
            latency_ms=0,
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
        response = self.complete(
            prompt,
            model_tier=model_tier,
            temperature=temperature,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
        )
        return parse_structured_response(response.text, schema)
