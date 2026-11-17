"""Giao diện LLM độc lập provider và lỗi có kiểu."""

from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from medgraph.models.llm import LLMResponse

ModelTier = Literal["small", "large"]
StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class LLMError(RuntimeError):
    """Lỗi provider hoặc kết nối LLM."""


class LLMOutputError(LLMError):
    """Phản hồi LLM không khớp schema yêu cầu."""


class LLMClient(Protocol):
    @property
    def provider(self) -> str: ...

    def model_for_tier(self, model_tier: ModelTier) -> str: ...

    def complete(
        self,
        prompt: str,
        *,
        model_tier: ModelTier,
        temperature: float,
        prompt_name: str | None = None,
        prompt_version: str | None = None,
    ) -> LLMResponse: ...

    def complete_structured(
        self,
        prompt: str,
        schema: type[StructuredModel],
        *,
        model_tier: ModelTier,
        temperature: float,
        prompt_name: str | None = None,
        prompt_version: str | None = None,
    ) -> StructuredModel: ...


def parse_structured_response(text: str, schema: type[StructuredModel]) -> StructuredModel:
    """Kiểm tra JSON do provider trả về theo schema Pydantic."""
    try:
        return schema.model_validate_json(text)
    except ValidationError as exc:
        raise LLMOutputError(f"LLM output does not match {schema.__name__}") from exc
