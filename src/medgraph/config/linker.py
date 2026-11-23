"""Nạp ngưỡng linking từ YAML."""

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class LinkerSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    bm25_min_score: float = Field(ge=0)
    embedding_min_similarity: float = Field(ge=0, le=1)
    embedding_model: str = Field(min_length=1)


def load_linker_settings(path: Path = Path("config/ranking.yaml")) -> LinkerSettings:
    with path.open(encoding="utf-8") as stream:
        data = yaml.safe_load(stream)
    return LinkerSettings.model_validate(data["linker"])
