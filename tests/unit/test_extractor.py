"""F-021: đầu ra của extractor và các lỗi tại biên LLM."""

import json
from unicodedata import normalize
from unittest.mock import patch

import pytest

from medgraph.llm.base import LLMError, LLMOutputError
from medgraph.llm.prompts import PromptError, PromptRegistry, PromptTemplate
from medgraph.llm.providers.fake import FakeLLMClient
from medgraph.models.extraction import ExtractionResult
from medgraph.models.schemas import Entity
from medgraph.nlp.extractor import EntityExtractor

pytestmark = pytest.mark.unit


@pytest.fixture
def template() -> PromptTemplate:
    return PromptRegistry().get("extract", "v1")


def test_extracts_attributes_per_mention_in_one_versioned_call(template: PromptTemplate) -> None:
    narrative = "Tôi ho nhẹ 3 ngày, không sốt, đau ngực từ sáng nay. Máy đo SpO₂ 96%, CRP 8,5 mg/L."
    mentions = [
        {"text": "ho nhẹ 3 ngày", "type": "symptom", "duration_days": 3, "severity": "nhẹ"},
        {"text": "không sốt", "type": "symptom", "negated": True},
        {"text": "đau ngực từ sáng nay", "type": "symptom"},
        {"text": "SpO₂ 96%", "type": "lab", "value": 96, "unit": "%"},
        {"text": "CRP 8,5 mg/L", "type": "lab", "value": 8.5, "unit": "mg/L"},
    ]
    client = FakeLLMClient([json.dumps({"entities": mentions}, ensure_ascii=False)])
    with patch.object(client, "complete_structured", wraps=client.complete_structured) as call:
        result = EntityExtractor(client, template).extract(normalize("NFD", narrative))

    call.assert_called_once_with(
        template.render(narrative_json=json.dumps(narrative, ensure_ascii=False)),
        ExtractionResult,
        model_tier="small",
        temperature=0.0,
        prompt_name="extract",
        prompt_version="v1",
    )
    assert client.call_count == 1
    assert json.loads(result.model_dump_json()) == {
        "entities": [Entity.model_validate(m).model_dump(mode="json") for m in mentions]
    }


@pytest.mark.parametrize(("text", "calls"), [("Xin chào!", 1), (" \n ", 0)])
def test_valid_empty_result(template: PromptTemplate, text: str, calls: int) -> None:
    client = FakeLLMClient(['{"entities":[]}'])
    assert EntityExtractor(client, template).extract(text).model_dump_json() == '{"entities":[]}'
    assert client.call_count == calls


@pytest.mark.parametrize(
    "output",
    [
        "invalid json",
        "{}",
        '{"entities":{}}',
        '{"entities":[{"type":"symptom"}]}',
        '{"entities":[{"text":"ho","type":"symptom","id":"HP:0012735"}]}',
        '{"entities":[{"text":"ho","type":"symptom","duration_days":-1}]}',
        '{"entities":[{"text":"ho","type":"symptom","negated":"false"}]}',
        '{"entities":[{"text":"ho","type":"symptom","unknown":1}]}',
        '{"entities":[{"text":"sốt","type":"symptom"}]}',
    ],
)
def test_invalid_output_raises_instead_of_returning_empty(
    template: PromptTemplate, output: str
) -> None:
    extractor = EntityExtractor(FakeLLMClient([output]), template)
    with pytest.raises(LLMOutputError):
        extractor.extract("Tôi ho")


def test_provider_failure_propagates(template: PromptTemplate) -> None:
    extractor = EntityExtractor(FakeLLMClient(), template)
    with pytest.raises(LLMError, match="no queued response"):
        extractor.extract("Tôi ho")


def test_incompatible_prompt_rejected() -> None:
    with pytest.raises(PromptError, match="ExtractionResult"):
        EntityExtractor(FakeLLMClient(), PromptRegistry().get("build_aliases", "v1"))
