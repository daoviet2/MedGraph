"""Đầu ra NER trước bước liên kết thực thể."""

from typing import Literal
from unicodedata import normalize

from pydantic import BaseModel, ConfigDict, field_validator

from medgraph.models.schemas import Entity, EntityType


class ExtractedEntity(Entity):
    """Mention được trích nguyên văn, chưa gán mã ontology."""

    model_config = ConfigDict(strict=True, allow_inf_nan=False)

    id: None = None
    type: Literal[EntityType.SYMPTOM, EntityType.RISK, EntityType.LAB, EntityType.CONDITION]

    @field_validator("text", "severity", "unit")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        return normalize("NFC", value) if value is not None else None


class ExtractionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    entities: tuple[ExtractedEntity, ...]
