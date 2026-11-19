"""Value Objects cho bản nháp alias do LLM sinh và báo cáo tạo nháp."""

import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def normalize_alias(value: str) -> str:
    """Chuẩn hóa NFC, bỏ dấu, đổi đ thành d, chữ thường và gom khoảng trắng."""
    lowered = " ".join(unicodedata.normalize("NFC", value).casefold().split())
    decomposed = unicodedata.normalize("NFD", lowered.replace("đ", "d"))
    return unicodedata.normalize(
        "NFC", "".join(char for char in decomposed if not unicodedata.combining(char))
    )


class AliasDraft(BaseModel):
    """Một alias đề xuất trong JSON của LLM; chưa được chấp thuận."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_id: str = Field(min_length=1)
    alias: str = Field(min_length=1)

    @field_validator("entity_id", "alias")
    @classmethod
    def _clean_text(cls, value: str) -> str:
        cleaned = unicodedata.normalize("NFC", value.strip())
        if not cleaned or "\n" in cleaned or "\r" in cleaned:
            raise ValueError("must be nonempty single-line text")
        return cleaned


class AliasDraftBatch(BaseModel):
    """Lô alias do LLM đề xuất theo prompt ``build_aliases``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    aliases: tuple[AliasDraft, ...]


class AliasEntity(BaseModel):
    """Dữ liệu seed tối thiểu cho sinh alias; nguồn là của thực thể gốc."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_id: str
    entity_type: Literal["symptom", "disease"]
    name_vi: str
    source_id: str
    existing_aliases: tuple[str, ...]


class AliasDraftRow(BaseModel):
    """Dòng CSV nháp: luôn chờ rà soát và giữ nguồn của thực thể gốc."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_id: str
    entity_type: Literal["symptom", "disease"]
    alias: str
    alias_norm: str
    model: str
    prompt_version: str
    generated_at: str
    review_status: Literal["pending"] = "pending"
    reviewer_note: str = ""
    source_id: str
    provenance: Literal["auto_extracted"] = "auto_extracted"


class AliasBuildReport(BaseModel):
    """Số thực thể đã xử lý và số dòng nháp mới được ghi."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entities_processed: int = Field(ge=0)
    aliases_proposed: int = Field(ge=0)
    aliases_added: int = Field(ge=0)
