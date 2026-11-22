"""Trích thực thể từ một lời kể bằng một prompt có version."""

import json
from unicodedata import normalize

from medgraph.llm.base import LLMClient, LLMOutputError
from medgraph.llm.prompts import PromptError, PromptTemplate
from medgraph.models.extraction import ExtractionResult


class EntityExtractor:
    def __init__(self, client: LLMClient, template: PromptTemplate) -> None:
        if template.output_schema != ExtractionResult.__name__:
            raise PromptError("Extraction prompt must declare ExtractionResult")
        self._client = client
        self._template = template

    def extract(self, text: str) -> ExtractionResult:
        """Trả các mention theo hợp đồng; lỗi provider và lỗi đầu ra được truyền cho caller."""
        narrative = normalize("NFC", text)
        if not narrative.strip():
            return ExtractionResult(entities=())

        prompt = self._template.render(narrative_json=json.dumps(narrative, ensure_ascii=False))
        result = self._client.complete_structured(
            prompt,
            ExtractionResult,
            model_tier=self._template.model_tier,
            temperature=0.0,
            prompt_name=self._template.name,
            prompt_version=self._template.version,
        )
        for entity in result.entities:
            if not entity.text.strip() or entity.text not in narrative:
                raise LLMOutputError("Extracted text must be a nonblank span of the narrative")
        return result
