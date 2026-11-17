"""Hợp đồng phản hồi của LLM provider."""

from pydantic import BaseModel, ConfigDict, Field


class LLMResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    model: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    latency_ms: float = Field(ge=0)
