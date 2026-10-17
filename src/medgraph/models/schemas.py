"""Hợp đồng dữ liệu cốt lõi cho pipeline và API của MedGraph.

Đóng băng theo quy tắc R7 (AGENTS.md). Mọi module trao đổi qua các model Pydantic bất biến tại đây.
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION: str = "1.0.0"


class Urgency(StrEnum):
    """Mức độ khẩn cấp khuyến nghị cho người dùng."""

    EMERGENCY = "EMERGENCY"  # Dấu hiệu cấp cứu (red flags), cần gọi 115 hoặc đi viện ngay
    SEE_DOCTOR_SOON = "SEE_DOCTOR_SOON"  # Nên khám chuyên khoa trong vài ngày
    MONITOR = "MONITOR"  # Theo dõi triệu chứng tại nhà, đi khám nếu tăng nặng
    SELF_CARE_INFO = "SELF_CARE_INFO"  # Thông tin chăm sóc chung, không có dấu hiệu đáng ngại


class EntityType(StrEnum):
    """Loại thực thể y khoa nhận diện từ văn bản."""

    SYMPTOM = "symptom"
    RISK = "risk"
    LAB = "lab"
    DRUG = "drug"
    CONDITION = "condition"


class Provenance(StrEnum):
    """Nguồn gốc và mức độ tin cậy của quan hệ/dữ liệu."""

    CURATED = "curated"  # Nhập tay trực tiếp từ guideline/nguồn uy tín
    REVIEWED = "reviewed"  # Trích xuất tự động và đã được chuyên môn rà soát
    AUTO_EXTRACTED = "auto_extracted"  # Do LLM trích xuất tự động, chưa rà soát


class ReviewStatus(StrEnum):
    """Trạng thái duyệt của dữ liệu y khoa."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Entity(BaseModel):
    """Thực thể y khoa được trích xuất từ văn bản người dùng."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(min_length=1, description="Chuỗi văn bản gốc người dùng nhập")
    id: str | None = Field(default=None, description="Mã chuẩn hóa (HPO, UMLS, ICD10,...)")
    type: EntityType = Field(description="Loại thực thể y khoa")
    negated: bool = Field(default=False, description="Người dùng phủ nhận có thực thể này")
    duration_days: int | None = Field(
        default=None, ge=0, description="Thời gian kéo dài tính bằng ngày"
    )
    severity: str | None = Field(default=None, description="Mức độ nghiêm trọng (nhẹ, vừa, nặng)")
    value: float | None = Field(
        default=None, description="Giá trị định lượng (chỉ số xét nghiệm, sinh hiệu)"
    )
    unit: str | None = Field(default=None, description="Đơn vị đo lường tương ứng với value")


class Citation(BaseModel):
    """Thông tin trích dẫn nguồn bằng chứng y khoa."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: str = Field(
        min_length=1, description="ID của chunk tài liệu y khoa trong vector store"
    )
    source_id: str | None = Field(
        default=None, description="ID nguồn tài liệu (trỏ tới sources.csv)"
    )
    supported: bool | None = Field(
        default=None,
        description="Kết quả kiểm tra xác thực lớp 2: nguồn có ủng hộ nhận định không",
    )


class Claim(BaseModel):
    """Nhận định y khoa do LLM sinh ra kèm trích dẫn kiểm chứng."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(min_length=1, description="Nội dung nhận định y khoa")
    citation: Citation = Field(description="Bằng chứng trích dẫn nguồn")

    @field_validator("text")
    @classmethod
    def validate_text_not_blank(cls, v: str) -> str:
        """Đảm bảo nội dung nhận định không rỗng hoặc chỉ chứa khoảng trắng."""
        if not v.strip():
            raise ValueError("Claim text không được để trống")
        return v


class Candidate(BaseModel):
    """Bệnh ứng viên được đề xuất từ Knowledge Graph."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    disease_id: str = Field(min_length=1, description="Mã định danh bệnh (ICD-10, UMLS)")
    name_vi: str = Field(min_length=1, description="Tên bệnh tiếng Việt")
    likelihood: float = Field(
        ge=0.0, le=1.0, description="Xác suất / điểm khả năng từ graph ranking [0, 1]"
    )
    danger_level: int = Field(
        ge=1, le=3, description="Mức độ nguy hiểm (1: nhẹ, 2: trung bình, 3: nguy cấp)"
    )
    cant_miss: bool = Field(
        default=False, description="Bệnh thuộc danh sách bắt buộc không được bỏ sót"
    )
    matched_symptoms: list[str] = Field(
        default_factory=list, description="Danh sách triệu chứng khớp"
    )
    provenance_mix: dict[Provenance, int] = Field(
        default_factory=dict,
        description="Thống kê nguồn gốc của các cạnh dẫn tới bệnh",
    )
    claims: list[Claim] = Field(
        default_factory=list, description="Các nhận định kèm trích dẫn minh chứng"
    )


class SubgraphNode(BaseModel):
    """Node trong đồ thị con phục vụ trực quan hóa đường suy luận."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1, description="Định danh node")
    label: str = Field(min_length=1, description="Nhãn node (Symptom, Disease, RiskFactor,...)")
    name: str = Field(min_length=1, description="Tên hiển thị tiếng Việt")
    properties: dict[str, Any] = Field(default_factory=dict, description="Các thuộc tính bổ sung")


class SubgraphEdge(BaseModel):
    """Cạnh trong đồ thị con biểu diễn quan hệ giữa các thực thể."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str = Field(min_length=1, description="ID node nguồn")
    target: str = Field(min_length=1, description="ID node đích")
    type: str = Field(min_length=1, description="Loại quan hệ (INDICATES, HAS_RISK_FACTOR,...)")
    weight: float | None = Field(default=None, description="Trọng số liên kết")
    properties: dict[str, Any] = Field(default_factory=dict, description="Các thuộc tính bổ sung")


class Subgraph(BaseModel):
    """Đồ thị con biểu diễn đường suy luận Triệu chứng -> Bệnh."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    nodes: list[SubgraphNode] = Field(default_factory=list, description="Danh sách các node")
    edges: list[SubgraphEdge] = Field(default_factory=list, description="Danh sách các cạnh")


class Result(BaseModel):
    """Kết quả phân tích đầy đủ trả về từ pipeline /analyze."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field(default=SCHEMA_VERSION, description="Phiên bản schema")
    abstained: bool = Field(
        description="True nếu hệ thống từ chối xếp hạng do không đủ dữ liệu/tự tin"
    )
    urgency: Urgency = Field(description="Mức độ khẩn cấp khuyến nghị")
    red_flags: list[str] = Field(
        default_factory=list, description="Danh sách cảnh báo cấp cứu (red flags)"
    )
    entities: list[Entity] = Field(
        default_factory=list, description="Danh sách thực thể trích xuất"
    )
    likely: list[Candidate] = Field(
        default_factory=list, description="Các bệnh có khả năng cao nhất"
    )
    cant_miss: list[Candidate] = Field(
        default_factory=list, description="Các bệnh nguy hiểm cần loại trừ"
    )
    follow_up_questions: list[str] = Field(
        default_factory=list, description="Các câu hỏi làm rõ tiếp theo"
    )
    subgraph: Subgraph = Field(
        default_factory=Subgraph, description="Đồ thị con giải thích suy luận"
    )
    disclaimer: str = Field(min_length=1, description="Khuyến cáo y khoa bắt buộc")

    @field_validator("disclaimer")
    @classmethod
    def validate_disclaimer_not_blank(cls, v: str) -> str:
        """Đảm bảo disclaimer không rỗng hoặc chỉ toàn khoảng trắng."""
        if not v.strip():
            raise ValueError("Disclaimer không được để trống")
        return v
