"""Hợp đồng bản ghi nạp Knowledge Graph (MedGraph).

Ranh giới giữa tầng nạp dữ liệu (seed CSV/ETL) và đồ thị Neo4j theo docs/04 §1-2.
Đóng băng theo quy tắc R7 (AGENTS.md). 100% Value Objects bất biến (frozen=True, extra="forbid").
"""

import unicodedata
from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from medgraph.models.schemas import Provenance, ReviewStatus, Urgency


def _normalize_string_value(v: str) -> str:
    """Chuẩn hóa chuỗi văn bản theo chuẩn Unicode NFC và cắt khoảng trắng đầu cuối."""
    return unicodedata.normalize("NFC", v).strip()


class RecordBase(BaseModel):
    """Lớp cơ sở cho toàn bộ bản ghi đồ thị, hỗ trợ chuẩn hóa chuỗi và bất biến."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _normalize_fields(cls, data: Any) -> Any:
        """Tự động chuẩn hóa NFC và strip mọi trường chuỗi và danh sách chuỗi."""
        if isinstance(data, dict):
            normalized: dict[str, Any] = {}
            for k, v in data.items():
                if isinstance(v, str):
                    normalized[k] = _normalize_string_value(v)
                elif isinstance(v, list):
                    normalized_list: list[Any] = []
                    for item in v:
                        if isinstance(item, str):
                            cleaned = _normalize_string_value(item)
                            if cleaned:  # loại bỏ chuỗi rỗng sau khi strip
                                normalized_list.append(cleaned)
                        else:
                            normalized_list.append(item)
                    normalized[k] = normalized_list
                else:
                    normalized[k] = v
            return normalized
        return data


# =============================================================================
# Node Records (docs/04 §1)
# =============================================================================


class NodeRecord(RecordBase):
    """Lớp cơ sở cho mọi node trong Knowledge Graph."""

    review_status: ReviewStatus = Field(
        default=ReviewStatus.PENDING,
        description="Trạng thái kiểm duyệt chuyên môn y khoa",
    )


class SymptomRecord(NodeRecord):
    """Bản ghi triệu chứng (Symptom node).

    Lưu ý: idf KHÔNG nằm trong record này; idf là thuộc tính tính toán sau khi nạp (F-014).
    """

    id: str = Field(
        pattern=r"^(HP|UMLS):",
        description="Định danh triệu chứng theo chuẩn HPO hoặc UMLS",
    )
    name_en: str = Field(min_length=1, description="Tên triệu chứng tiếng Anh")
    name_vi: str = Field(min_length=1, description="Tên triệu chứng tiếng Việt")
    aliases_vi: list[str] = Field(
        default_factory=list, description="Danh sách tên gọi / biến thể tiếng Việt"
    )
    is_red_flag: bool = Field(default=False, description="Dấu hiệu cảnh báo cấp cứu (red flag)")


class DiseaseRecord(NodeRecord):
    """Bản ghi bệnh lý (Disease node)."""

    id: str = Field(
        pattern=r"^(ICD10|UMLS):",
        description="Định danh bệnh theo chuẩn ICD-10 hoặc UMLS",
    )
    name_en: str = Field(min_length=1, description="Tên bệnh tiếng Anh")
    name_vi: str = Field(min_length=1, description="Tên bệnh tiếng Việt")
    aliases_vi: list[str] = Field(
        default_factory=list, description="Danh sách tên gọi / biến thể tiếng Việt"
    )
    category: str = Field(min_length=1, description="Nhóm bệnh lý (ví dụ: Nhiễm trùng hô hấp dưới)")
    urgency_default: Urgency = Field(description="Mức độ khẩn cấp mặc định")
    danger_level: int = Field(
        ge=1, le=3, description="Mức độ nguy hiểm (1: nhẹ, 2: trung bình, 3: nguy cấp)"
    )
    cant_miss: bool = Field(
        default=False,
        description="Bệnh nguy hiểm bắt buộc không được bỏ sót (cần loại trừ)",
    )


class RiskFactorRecord(NodeRecord):
    """Bản ghi yếu tố nguy cơ (RiskFactor node)."""

    id: str = Field(pattern=r"^RF:", description="Định danh yếu tố nguy cơ (bắt đầu bằng RF:)")
    name_vi: str = Field(min_length=1, description="Tên yếu tố nguy cơ tiếng Việt")
    type: str = Field(
        min_length=1,
        description="Phân loại nguy cơ (ví dụ: hành vi, tiếp xúc nghề nghiệp, cơ địa...)",
    )


class LabTestRecord(NodeRecord):
    """Bản ghi cận lâm sàng / xét nghiệm (LabTest node)."""

    id: str = Field(
        pattern=r"^(LOINC|LAB):",
        description="Định danh xét nghiệm theo LOINC hoặc mã nội bộ LAB:",
    )
    name_vi: str = Field(min_length=1, description="Tên xét nghiệm tiếng Việt")
    purpose: str = Field(min_length=1, description="Mục đích xét nghiệm")


class SourceDocRecord(NodeRecord):
    """Bản ghi tài liệu nguồn y khoa (SourceDoc node)."""

    id: str = Field(pattern=r"^SRC:", description="Định danh tài liệu nguồn (bắt đầu bằng SRC:)")
    title: str = Field(min_length=1, description="Tiêu đề tài liệu / hướng dẫn điều trị")
    publisher: str = Field(min_length=1, description="Cơ quan xuất bản (BYT, WHO, ATS,...)")
    year: int = Field(ge=1900, le=2100, description="Năm ban hành")
    url: str = Field(min_length=1, description="Đường dẫn tra cứu trực tuyến")
    license: str = Field(min_length=1, description="Giấy phép sử dụng tài liệu")
    effective_from: date | str = Field(description="Thời điểm bắt đầu có hiệu lực")
    effective_to: date | str | None = Field(
        default=None, description="Thời điểm hết hiệu lực nếu có"
    )
    status: str = Field(
        min_length=1, description="Trạng thái hiệu lực (active, superseded, draft,...)"
    )
    superseded_by: str | None = Field(
        default=None,
        pattern=r"^SRC:",
        description="ID tài liệu thay thế nếu status='superseded'",
    )

    @model_validator(mode="after")
    def validate_lifecycle_and_dates(self) -> "SourceDocRecord":
        """Kiểm tra tính nhất quán giữa khoảng thời gian và trạng thái thay thế."""
        if self.effective_to is not None:
            from_str = (
                self.effective_from.isoformat()
                if isinstance(self.effective_from, date)
                else str(self.effective_from)
            )
            to_str = (
                self.effective_to.isoformat()
                if isinstance(self.effective_to, date)
                else str(self.effective_to)
            )
            if to_str < from_str:
                raise ValueError(f"effective_to ({to_str}) phải >= effective_from ({from_str})")

        if self.status == "superseded":
            if not self.superseded_by:
                raise ValueError(
                    "status='superseded' bắt buộc phải có superseded_by trỏ tới tài liệu mới"
                )
            if self.superseded_by == self.id:
                raise ValueError("superseded_by không được trùng với chính id của tài liệu")

        return self


# =============================================================================
# Edge Records (docs/04 §2)
# =============================================================================


class EdgeRecord(RecordBase):
    """Lớp cơ sở cho mọi cạnh (relationship) trong Knowledge Graph.

    Quy tắc R3: mọi cạnh bắt buộc phải có source_id hợp lệ trỏ tới SourceDoc.
    """

    source_id: str = Field(
        pattern=r"^SRC:",
        description="ID nguồn tài liệu minh chứng bắt buộc (bắt đầu bằng SRC:)",
    )
    provenance: Provenance = Field(
        default=Provenance.CURATED,
        description="Nguồn gốc trích xuất (curated, reviewed, auto_extracted)",
    )
    evidence_count: int = Field(
        default=1,
        ge=1,
        description="Số lượng bằng chứng ủng hộ quan hệ (tối thiểu 1)",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Độ tin cậy của quan hệ [0, 1]",
    )


class IndicatesEdge(EdgeRecord):
    """Cạnh (Symptom)-[:INDICATES]->(Disease)."""

    symptom_id: str = Field(pattern=r"^(HP|UMLS):", description="Định danh triệu chứng nguồn")
    disease_id: str = Field(pattern=r"^(ICD10|UMLS):", description="Định danh bệnh đích")
    weight: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Trọng số liên kết Triệu chứng -> Bệnh [0, 1]",
    )
    is_cardinal: bool = Field(
        default=False,
        description="Triệu chứng cốt lõi / chỉ điểm của bệnh",
    )


class HasRiskFactorEdge(EdgeRecord):
    """Cạnh (Disease)-[:HAS_RISK_FACTOR]->(RiskFactor)."""

    disease_id: str = Field(pattern=r"^(ICD10|UMLS):", description="Định danh bệnh nguồn")
    risk_id: str = Field(pattern=r"^RF:", description="Định danh yếu tố nguy cơ đích")
    weight: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Trọng số ảnh hưởng của nguy cơ đối với bệnh [0, 1]",
    )


class ConfirmedByRole(StrEnum):
    """Vai trò của xét nghiệm cận lâm sàng đối với bệnh."""

    SCREENING = "screening"  # Sàng lọc ban đầu
    CONFIRMATORY = "confirmatory"  # Tiêu chuẩn vàng / chẩn đoán xác định


class ConfirmedByEdge(EdgeRecord):
    """Cạnh (Disease)-[:CONFIRMED_BY]->(LabTest)."""

    disease_id: str = Field(pattern=r"^(ICD10|UMLS):", description="Định danh bệnh nguồn")
    lab_id: str = Field(pattern=r"^(LOINC|LAB):", description="Định danh xét nghiệm đích")
    role: ConfirmedByRole = Field(
        description="Vai trò của xét nghiệm (screening hoặc confirmatory)"
    )


class DifferentialOfEdge(EdgeRecord):
    """Cạnh (Disease)-[:DIFFERENTIAL_OF]->(Disease)."""

    disease_id: str = Field(pattern=r"^(ICD10|UMLS):", description="Định danh bệnh nguồn")
    other_id: str = Field(
        pattern=r"^(ICD10|UMLS):", description="Định danh bệnh chẩn đoán phân biệt"
    )
    distinguishing_features: str = Field(
        min_length=1,
        description="Đặc điểm phân biệt lâm sàng giữa hai bệnh",
    )

    @model_validator(mode="after")
    def validate_not_self_referencing(self) -> "DifferentialOfEdge":
        """DifferentialOfEdge cấm tự trỏ chính nó."""
        if self.disease_id == self.other_id:
            raise ValueError(
                "DifferentialOfEdge cấm tự trỏ chính nó: disease_id == other_id "
                f"({self.disease_id})"
            )
        return self


class DocumentedInEdge(EdgeRecord):
    """Cạnh (Disease)-[:DOCUMENTED_IN]->(SourceDoc)."""

    disease_id: str = Field(pattern=r"^(ICD10|UMLS):", description="Định danh bệnh nguồn")
    source_doc_id: str = Field(pattern=r"^SRC:", description="Định danh tài liệu nguồn đích")
    section: str = Field(min_length=1, description="Mục / chương trong tài liệu (ví dụ: Chẩn đoán)")

    @model_validator(mode="before")
    @classmethod
    def _default_source_id(cls, data: Any) -> Any:
        """Nếu source_id bị khuyết, tự động gán bằng source_doc_id đích."""
        if isinstance(data, dict):
            if "source_id" not in data and "source_doc_id" in data:
                data["source_id"] = data["source_doc_id"]
        return data


class IsAEdge(EdgeRecord):
    """Cạnh quan hệ kế thừa phân cấp ontology (ví dụ: Symptom IS_A Symptom)."""

    child_id: str = Field(min_length=1, description="Định danh khái niệm con")
    parent_id: str = Field(min_length=1, description="Định danh khái niệm cha")

    @model_validator(mode="after")
    def validate_not_self_referencing(self) -> "IsAEdge":
        """IsAEdge cấm tự trỏ chính nó."""
        if self.child_id == self.parent_id:
            raise ValueError(
                f"IsAEdge cấm tự trỏ chính nó: child_id == parent_id ({self.child_id})"
            )
        return self


class SupersededByEdge(EdgeRecord):
    """Cạnh (SourceDoc)-[:SUPERSEDED_BY]->(SourceDoc)."""

    old_id: str = Field(pattern=r"^SRC:", description="Định danh tài liệu cũ bị thay thế")
    new_id: str = Field(pattern=r"^SRC:", description="Định danh tài liệu mới thay thế")
    effective_from: date | str = Field(description="Thời điểm bản mới bắt đầu có hiệu lực thay thế")

    @model_validator(mode="before")
    @classmethod
    def _default_source_id(cls, data: Any) -> Any:
        """Nếu source_id bị khuyết, tự động gán bằng new_id."""
        if isinstance(data, dict):
            if "source_id" not in data and "new_id" in data:
                data["source_id"] = data["new_id"]
        return data

    @model_validator(mode="after")
    def validate_not_self_referencing(self) -> "SupersededByEdge":
        """SupersededByEdge cấm tự trỏ chính nó."""
        if self.old_id == self.new_id:
            raise ValueError(
                f"SupersededByEdge cấm tự trỏ chính nó: old_id == new_id ({self.old_id})"
            )
        return self
