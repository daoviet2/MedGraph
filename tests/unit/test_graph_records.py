"""Unit tests cho hợp đồng bản ghi Knowledge Graph (models/graph_records.py).

Kiểm tra:
- Định dạng ID theo regex cho từng node và quan hệ.
- Chuẩn hóa Unicode NFC và strip khoảng trắng.
- Trường review_status và các giá trị enum.
- Không cho phép thuộc tính idf trong bản ghi SymptomRecord.
- EdgeRecord bắt buộc có source_id hợp lệ (^SRC:).
- Các ràng buộc giá trị: likelihood/weight/confidence [0, 1], danger_level [1, 3],
  evidence_count >= 1.
- Ràng buộc vòng đời SourceDocRecord: effective_to >= effective_from, status='superseded'
  bắt buộc có superseded_by.
- Ràng buộc chống tự trỏ (no self-reference): IsAEdge, DifferentialOfEdge,
  SupersededByEdge, SourceDocRecord.
- Tính bất biến (frozen=True) và từ chối trường lạ (extra="forbid").
"""

import unicodedata
from datetime import date

import pytest
from pydantic import ValidationError

from medgraph.models.graph_records import (
    ConfirmedByEdge,
    ConfirmedByRole,
    DifferentialOfEdge,
    DiseaseRecord,
    DocumentedInEdge,
    EdgeRecord,
    HasRiskFactorEdge,
    IndicatesEdge,
    IsAEdge,
    LabTestRecord,
    RiskFactorRecord,
    SourceDocRecord,
    SupersededByEdge,
    SymptomRecord,
)
from medgraph.models.schemas import Provenance, ReviewStatus, Urgency

pytestmark = pytest.mark.unit


# =============================================================================
# 1. SymptomRecord Tests
# =============================================================================


def test_symptom_record_valid() -> None:
    """Tạo SymptomRecord hợp lệ với HPO hoặc UMLS ID."""
    s1 = SymptomRecord(
        id="HP:0012735",
        name_en="Cough",
        name_vi="Ho",
        aliases_vi=["ho khan", "ho có đờm"],
        is_red_flag=False,
    )
    assert s1.id == "HP:0012735"
    assert s1.review_status == ReviewStatus.PENDING

    s2 = SymptomRecord(
        id="UMLS:C0010200",
        name_en="Hemoptysis",
        name_vi="Ho ra máu",
        is_red_flag=True,
        review_status=ReviewStatus.APPROVED,
    )
    assert s2.is_red_flag is True
    assert s2.review_status == ReviewStatus.APPROVED


def test_symptom_record_invalid_id() -> None:
    """ID không bắt đầu bằng HP: hoặc UMLS: bị từ chối."""
    with pytest.raises(ValidationError):
        SymptomRecord(
            id="ICD10:J18",
            name_en="Cough",
            name_vi="Ho",
        )

    with pytest.raises(ValidationError):
        SymptomRecord(
            id="INVALID:001",
            name_en="Cough",
            name_vi="Ho",
        )


def test_symptom_record_rejects_idf() -> None:
    """idf KHÔNG nằm trong record (F-014), truyền vào phải bị từ chối do extra='forbid'."""
    with pytest.raises(ValidationError):
        SymptomRecord(
            id="HP:0012735",
            name_en="Cough",
            name_vi="Ho",
            idf=1.85,  # type: ignore[call-arg]
        )


# =============================================================================
# 2. DiseaseRecord Tests
# =============================================================================


def test_disease_record_valid() -> None:
    """Tạo DiseaseRecord hợp lệ với ICD10 hoặc UMLS ID."""
    d = DiseaseRecord(
        id="ICD10:J18.9",
        name_en="Pneumonia, unspecified",
        name_vi="Viêm phổi",
        aliases_vi=["viêm phổi mắc phải cộng đồng", "viêm phế quản phổi"],
        category="Nhiễm trùng hô hấp dưới",
        urgency_default=Urgency.SEE_DOCTOR_SOON,
        danger_level=2,
        cant_miss=True,
    )
    assert d.id == "ICD10:J18.9"
    assert d.danger_level == 2
    assert d.cant_miss is True
    assert d.review_status == ReviewStatus.PENDING


def test_disease_record_invalid_id() -> None:
    """ID không bắt đầu bằng ICD10: hoặc UMLS: bị từ chối."""
    with pytest.raises(ValidationError):
        DiseaseRecord(
            id="HP:0012735",
            name_en="Pneumonia",
            name_vi="Viêm phổi",
            category="Nhiễm trùng",
            urgency_default=Urgency.MONITOR,
            danger_level=1,
        )


def test_disease_record_danger_level_bounds() -> None:
    """danger_level phải nằm trong khoảng [1, 3]."""
    for invalid_val in [0, 4, -1]:
        with pytest.raises(ValidationError):
            DiseaseRecord(
                id="ICD10:J18",
                name_en="Pneumonia",
                name_vi="Viêm phổi",
                category="Nhiễm trùng",
                urgency_default=Urgency.EMERGENCY,
                danger_level=invalid_val,
            )


# =============================================================================
# 3. RiskFactorRecord & LabTestRecord Tests
# =============================================================================


def test_risk_factor_record() -> None:
    """RiskFactorRecord bắt buộc id bắt đầu bằng RF:."""
    rf = RiskFactorRecord(id="RF:smoking", name_vi="Hút thuốc lá", type="Hành vi")
    assert rf.id == "RF:smoking"
    assert rf.review_status == ReviewStatus.PENDING

    with pytest.raises(ValidationError):
        RiskFactorRecord(id="SMOKING", name_vi="Hút thuốc", type="Hành vi")


def test_lab_test_record() -> None:
    """LabTestRecord chấp nhận LOINC: hoặc LAB:."""
    lab1 = LabTestRecord(
        id="LOINC:1988-5",
        name_vi="Định lượng CRP huyết thanh",
        purpose="Đánh giá phản ứng viêm",
    )
    assert lab1.id == "LOINC:1988-5"

    lab2 = LabTestRecord(
        id="LAB:xray_chest",
        name_vi="X-quang ngực thẳng",
        purpose="Phát hiện tổn thương thâm nhiễm",
    )
    assert lab2.id == "LAB:xray_chest"

    with pytest.raises(ValidationError):
        LabTestRecord(id="TEST:xray", name_vi="X-quang", purpose="Chẩn đoán")


# =============================================================================
# 4. SourceDocRecord Tests
# =============================================================================


def test_source_doc_record_valid() -> None:
    """Tạo SourceDocRecord hợp lệ."""
    doc = SourceDocRecord(
        id="SRC:BYT_2020_COPD",
        title="Hướng dẫn chẩn đoán và điều trị COPD",
        publisher="Bộ Y tế Việt Nam",
        year=2020,
        url="https://kcb.vn/van-ban/copd-2020.html",
        license="CC-BY-4.0",
        effective_from="2020-01-01",
        effective_to=None,
        status="active",
        superseded_by=None,
    )
    assert doc.id == "SRC:BYT_2020_COPD"
    assert doc.status == "active"
    assert doc.review_status == ReviewStatus.PENDING


def test_source_doc_date_validation() -> None:
    """effective_to phải >= effective_from."""
    with pytest.raises(ValidationError):
        SourceDocRecord(
            id="SRC:DOC1",
            title="Tài liệu cũ",
            publisher="BYT",
            year=2020,
            url="https://example.com",
            license="Public",
            effective_from="2020-01-01",
            effective_to="2019-12-31",  # Lỗi: trước ngày bắt đầu
            status="superseded",
            superseded_by="SRC:DOC2",
        )

    # Cùng ngày thì hợp lệ
    doc_same_day = SourceDocRecord(
        id="SRC:DOC1",
        title="Tài liệu 1 ngày",
        publisher="BYT",
        year=2020,
        url="https://example.com",
        license="Public",
        effective_from="2020-01-01",
        effective_to="2020-01-01",
        status="superseded",
        superseded_by="SRC:DOC2",
    )
    assert doc_same_day.effective_to == "2020-01-01"

    # date object hợp lệ
    doc_dates = SourceDocRecord(
        id="SRC:DOC1",
        title="Tài liệu date",
        publisher="BYT",
        year=2020,
        url="https://example.com",
        license="Public",
        effective_from=date(2020, 1, 1),
        effective_to=date(2025, 1, 1),
        status="active",
    )
    assert doc_dates.year == 2020


def test_source_doc_superseded_validation() -> None:
    """status='superseded' bắt buộc có superseded_by và không được trùng với chính nó."""
    # Thiếu superseded_by khi status='superseded'
    with pytest.raises(ValidationError):
        SourceDocRecord(
            id="SRC:DOC1",
            title="Tài liệu hết hạn",
            publisher="BYT",
            year=2015,
            url="https://example.com",
            license="Public",
            effective_from="2015-01-01",
            status="superseded",
            superseded_by=None,
        )

    # superseded_by tự trỏ chính nó
    with pytest.raises(ValidationError):
        SourceDocRecord(
            id="SRC:DOC1",
            title="Tài liệu tự thay thế",
            publisher="BYT",
            year=2015,
            url="https://example.com",
            license="Public",
            effective_from="2015-01-01",
            status="superseded",
            superseded_by="SRC:DOC1",
        )


# =============================================================================
# 5. Unicode NFC Normalization and Stripping Tests
# =============================================================================


def test_string_nfc_and_strip() -> None:
    """Mọi chuỗi tiếng Việt được chuẩn hóa NFC và strip khoảng trắng."""
    nfd_vi = unicodedata.normalize("NFD", "Việt Nam")
    assert unicodedata.is_normalized("NFC", nfd_vi) is False

    record = SymptomRecord(
        id="HP:0012735",
        name_en="  Cough  ",
        name_vi=f"   {nfd_vi}   ",
        aliases_vi=["  ho khan  ", "   ", "ho có đờm  "],
    )

    assert record.name_en == "Cough"
    assert record.name_vi == unicodedata.normalize("NFC", "Việt Nam")
    assert unicodedata.is_normalized("NFC", record.name_vi) is True
    # Aliases rỗng bị loại bỏ, còn lại 2 phần tử được strip
    assert record.aliases_vi == ["ho khan", "ho có đờm"]


# =============================================================================
# 6. Edge Records & Source ID Tests
# =============================================================================


def test_edge_record_base_requires_source_id() -> None:
    """EdgeRecord bắt buộc có source_id hợp lệ (^SRC:)."""
    edge = EdgeRecord(
        source_id="SRC:BYT_2020",
        provenance=Provenance.REVIEWED,
        evidence_count=2,
        confidence=0.9,
    )
    assert edge.source_id == "SRC:BYT_2020"
    assert edge.provenance == Provenance.REVIEWED
    assert edge.evidence_count == 2
    assert edge.confidence == 0.9

    # Thiếu source_id
    with pytest.raises(ValidationError):
        EdgeRecord()  # type: ignore[call-arg]

    # source_id sai định dạng
    with pytest.raises(ValidationError):
        EdgeRecord(source_id="INVALID_SOURCE")


def test_edge_record_confidence_and_evidence_count_bounds() -> None:
    """confidence trong [0, 1] và evidence_count >= 1."""
    with pytest.raises(ValidationError):
        EdgeRecord(source_id="SRC:01", confidence=1.2)

    with pytest.raises(ValidationError):
        EdgeRecord(source_id="SRC:01", confidence=-0.1)

    with pytest.raises(ValidationError):
        EdgeRecord(source_id="SRC:01", evidence_count=0)


def test_indicates_edge() -> None:
    """IndicatesEdge kết nối Symptom -> Disease."""
    edge = IndicatesEdge(
        symptom_id="HP:0012735",
        disease_id="ICD10:J18.9",
        weight=0.85,
        is_cardinal=True,
        source_id="SRC:BYT_2020",
    )
    assert edge.symptom_id == "HP:0012735"
    assert edge.disease_id == "ICD10:J18.9"
    assert edge.is_cardinal is True

    # Thiếu source_id bị từ chối
    with pytest.raises(ValidationError):
        IndicatesEdge(
            symptom_id="HP:0012735",
            disease_id="ICD10:J18.9",
            weight=0.8,
        )  # type: ignore[call-arg]

    # weight vượt quá 1.0
    with pytest.raises(ValidationError):
        IndicatesEdge(
            symptom_id="HP:0012735",
            disease_id="ICD10:J18.9",
            weight=1.5,
            source_id="SRC:01",
        )


def test_has_risk_factor_edge() -> None:
    """HasRiskFactorEdge kết nối Disease -> RiskFactor."""
    edge = HasRiskFactorEdge(
        disease_id="ICD10:J44",
        risk_id="RF:smoking",
        weight=0.9,
        source_id="SRC:GOLD_2023",
    )
    assert edge.risk_id == "RF:smoking"
    assert edge.weight == 0.9

    # ID sai định dạng
    with pytest.raises(ValidationError):
        HasRiskFactorEdge(
            disease_id="HP:001",
            risk_id="RF:smoking",
            source_id="SRC:01",
        )


def test_confirmed_by_edge() -> None:
    """ConfirmedByEdge kết nối Disease -> LabTest với role sàng lọc hoặc xác định."""
    edge = ConfirmedByEdge(
        disease_id="ICD10:J18",
        lab_id="LOINC:1988-5",
        role=ConfirmedByRole.CONFIRMATORY,
        source_id="SRC:BYT_2020",
    )
    assert edge.role == ConfirmedByRole.CONFIRMATORY

    edge_str = ConfirmedByEdge(
        disease_id="ICD10:J18",
        lab_id="LAB:xray",
        role="screening",  # type: ignore[arg-type]
        source_id="SRC:BYT_2020",
    )
    assert edge_str.role == ConfirmedByRole.SCREENING

    # Role không nằm trong {screening, confirmatory}
    with pytest.raises(ValidationError):
        ConfirmedByEdge(
            disease_id="ICD10:J18",
            lab_id="LOINC:1988-5",
            role="diagnostic",  # type: ignore[arg-type]
            source_id="SRC:BYT_2020",
        )


def test_differential_of_edge_no_self_referencing() -> None:
    """DifferentialOfEdge cấm tự trỏ chính nó."""
    diff = DifferentialOfEdge(
        disease_id="ICD10:J18",
        other_id="ICD10:J20",
        distinguishing_features="X-quang có hình ảnh đông đặc phổi",
        source_id="SRC:BYT_2020",
    )
    assert diff.disease_id == "ICD10:J18"

    # disease_id == other_id
    with pytest.raises(ValidationError):
        DifferentialOfEdge(
            disease_id="ICD10:J18",
            other_id="ICD10:J18",
            distinguishing_features="Không phân biệt được",
            source_id="SRC:BYT_2020",
        )


def test_documented_in_edge() -> None:
    """DocumentedInEdge kết nối Disease -> SourceDoc, tự động gán source_id nếu khuyết."""
    doc_edge = DocumentedInEdge(
        disease_id="ICD10:J44",
        source_doc_id="SRC:GOLD_2023",
        section="Chẩn đoán xác định",
    )
    assert doc_edge.source_id == "SRC:GOLD_2023"
    assert doc_edge.section == "Chẩn đoán xác định"


def test_is_a_edge_no_self_referencing() -> None:
    """IsAEdge cấm tự trỏ chính nó."""
    edge = IsAEdge(
        child_id="HP:0002094",  # Dyspnea
        parent_id="HP:0012735",
        source_id="SRC:HPO_ONTOLOGY",
    )
    assert edge.child_id != edge.parent_id

    # child_id == parent_id
    with pytest.raises(ValidationError):
        IsAEdge(
            child_id="HP:0012735",
            parent_id="HP:0012735",
            source_id="SRC:HPO",
        )


def test_superseded_by_edge_no_self_referencing() -> None:
    """SupersededByEdge cấm tự trỏ chính nó."""
    edge = SupersededByEdge(
        old_id="SRC:BYT_2015",
        new_id="SRC:BYT_2020",
        effective_from="2020-01-01",
    )
    assert edge.source_id == "SRC:BYT_2020"

    # old_id == new_id
    with pytest.raises(ValidationError):
        SupersededByEdge(
            old_id="SRC:BYT_2020",
            new_id="SRC:BYT_2020",
            effective_from="2020-01-01",
        )


# =============================================================================
# 7. Immutability (frozen=True) and Extra Forbidden Tests
# =============================================================================


def test_records_are_frozen() -> None:
    """Bản ghi là Value Object bất biến (frozen=True)."""
    s = SymptomRecord(
        id="HP:0012735",
        name_en="Cough",
        name_vi="Ho",
    )
    with pytest.raises(ValidationError):
        s.name_vi = "Ho khan"  # type: ignore[misc]


def test_records_forbid_extra_fields() -> None:
    """Bản ghi từ chối trường lạ không khai báo (extra='forbid')."""
    with pytest.raises(ValidationError):
        DiseaseRecord(
            id="ICD10:J18",
            name_en="Pneumonia",
            name_vi="Viêm phổi",
            category="Nhiễm trùng",
            urgency_default=Urgency.EMERGENCY,
            danger_level=2,
            extra_field="unknown",  # type: ignore[call-arg]
        )
