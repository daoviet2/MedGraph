"""Unit tests kiểm tra toàn vẹn dữ liệu seed_validator.py (F-011).

Kiểm tra:
- Dữ liệu hợp lệ không có lỗi.
- Bắt đúng mã lỗi DUPLICATE_ID khi trùng khóa.
- Bắt đúng mã lỗi DANGLING_* khi trỏ tới thực thể không tồn tại.
- Bắt đúng mã lỗi UNKNOWN_SOURCE_ID khi source_id không có trong sources.csv.
- Bắt đúng mã lỗi CYCLE_IS_A và CYCLE_SUPERSEDED_BY khi có chu trình.
- Bắt đúng mã lỗi DISEASE_WITHOUT_INDICATES và cảnh báo DISEASE_NO_CARDINAL_SYMPTOM.
"""

from pathlib import Path

import pytest

from medgraph.graph.seed_reader import SeedBundle, read_seed
from medgraph.graph.seed_validator import IssueLevel, validate_seed_bundle
from medgraph.models.graph_records import (
    ConfirmedByEdge,
    ConfirmedByRole,
    DiseaseRecord,
    DocumentedInEdge,
    HasRiskFactorEdge,
    IndicatesEdge,
    IsAEdge,
    SupersededByEdge,
    SymptomRecord,
)
from medgraph.models.schemas import Urgency

pytestmark = pytest.mark.unit

VALID_SEED_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "seed_mini" / "valid"


@pytest.fixture
def valid_bundle() -> SeedBundle:
    """Fixture nạp gói dữ liệu hợp lệ."""
    return read_seed(VALID_SEED_DIR)


def test_valid_bundle_has_no_issues(valid_bundle: SeedBundle) -> None:
    """Gói seed hợp lệ không phát sinh bất kỳ lỗi hoặc cảnh báo nào."""
    issues = validate_seed_bundle(valid_bundle)
    assert len(issues) == 0


def test_duplicate_id_detection(valid_bundle: SeedBundle) -> None:
    """Phát hiện trùng lặp ID trong danh sách thực thể (DUPLICATE_ID)."""
    dup_symptom = SymptomRecord(
        id=valid_bundle.symptoms[0].id,  # Trùng ID với phần tử đầu
        name_en="Duplicate Cough",
        name_vi="Ho trùng lặp",
    )
    bundle = valid_bundle.model_copy(update={"symptoms": valid_bundle.symptoms + [dup_symptom]})

    issues = validate_seed_bundle(bundle)
    dup_issues = [i for i in issues if i.code == "DUPLICATE_ID"]
    assert len(dup_issues) == 1
    assert dup_issues[0].level == IssueLevel.ERROR
    assert "symptoms.csv" in dup_issues[0].location


def test_unknown_source_id_detection(valid_bundle: SeedBundle) -> None:
    """Phát hiện cạnh sử dụng source_id không tồn tại (UNKNOWN_SOURCE_ID)."""
    bad_edge = IndicatesEdge(
        symptom_id="HP:0012735",
        disease_id="ICD10:J18",
        weight=0.8,
        source_id="SRC:UNKNOWN_DOC",
    )
    bundle = valid_bundle.model_copy(update={"indicates": valid_bundle.indicates + [bad_edge]})

    issues = validate_seed_bundle(bundle)
    source_issues = [i for i in issues if i.code == "UNKNOWN_SOURCE_ID"]
    assert len(source_issues) == 1
    assert source_issues[0].level == IssueLevel.ERROR
    assert "SRC:UNKNOWN_DOC" in source_issues[0].message


def test_dangling_references_detection(valid_bundle: SeedBundle) -> None:
    """Phát hiện các cạnh trỏ tới ID không tồn tại (DANGLING_*)."""
    # 1. Dangling symptom_id và disease_id
    bad_indicates = IndicatesEdge(
        symptom_id="HP:9999999",
        disease_id="ICD10:J99",
        weight=0.5,
        source_id="SRC:BYT_2020",
    )
    # 2. Dangling risk_id
    bad_risk = HasRiskFactorEdge(
        disease_id="ICD10:J18",
        risk_id="RF:unknown",
        weight=0.5,
        source_id="SRC:BYT_2020",
    )
    # 3. Dangling lab_id
    bad_lab = ConfirmedByEdge(
        disease_id="ICD10:J18",
        lab_id="LOINC:9999-9",
        role=ConfirmedByRole.CONFIRMATORY,
        source_id="SRC:BYT_2020",
    )
    # 4. Dangling source_doc_id
    bad_doc = DocumentedInEdge(
        disease_id="ICD10:J18",
        source_doc_id="SRC:NON_EXISTENT",
        section="Chẩn đoán",
        source_id="SRC:BYT_2020",
    )

    bundle = valid_bundle.model_copy(
        update={
            "indicates": valid_bundle.indicates + [bad_indicates],
            "has_risk_factors": valid_bundle.has_risk_factors + [bad_risk],
            "confirmed_by": valid_bundle.confirmed_by + [bad_lab],
            "documented_in": valid_bundle.documented_in + [bad_doc],
        }
    )

    issues = validate_seed_bundle(bundle)
    codes = {i.code for i in issues}

    assert "DANGLING_SYMPTOM_ID" in codes
    assert "DANGLING_DISEASE_ID" in codes
    assert "DANGLING_RISK_ID" in codes
    assert "DANGLING_LAB_ID" in codes
    assert "DANGLING_SOURCE_DOC_ID" in codes


def test_cycle_detection_in_is_a(valid_bundle: SeedBundle) -> None:
    """Phát hiện chu trình trong quan hệ kế thừa IS_A (CYCLE_IS_A)."""
    # Tạo chu trình: HP:0012735 -> HP:0001945 -> HP:0012735
    cycle_edges = [
        IsAEdge(
            child_id="HP:0012735",
            parent_id="HP:0001945",
            source_id="SRC:BYT_2020",
        ),
        IsAEdge(
            child_id="HP:0001945",
            parent_id="HP:0012735",
            source_id="SRC:BYT_2020",
        ),
    ]
    bundle = valid_bundle.model_copy(update={"is_a": cycle_edges})

    issues = validate_seed_bundle(bundle)
    cycle_issues = [i for i in issues if i.code == "CYCLE_IS_A"]
    assert len(cycle_issues) >= 1
    assert cycle_issues[0].level == IssueLevel.ERROR


def test_cycle_detection_in_superseded_by(valid_bundle: SeedBundle) -> None:
    """Phát hiện chu trình trong quan hệ thay thế SUPERSEDED_BY (CYCLE_SUPERSEDED_BY)."""
    # Tạo chu trình: SRC:BYT_2015 -> SRC:BYT_2020 -> SRC:BYT_2015
    cycle_edges = [
        SupersededByEdge(
            old_id="SRC:BYT_2015",
            new_id="SRC:BYT_2020",
            effective_from="2020-01-01",
        ),
        SupersededByEdge(
            old_id="SRC:BYT_2020",
            new_id="SRC:BYT_2015",
            effective_from="2021-01-01",
        ),
    ]
    bundle = valid_bundle.model_copy(update={"superseded_by": cycle_edges})

    issues = validate_seed_bundle(bundle)
    cycle_issues = [i for i in issues if i.code == "CYCLE_SUPERSEDED_BY"]
    assert len(cycle_issues) >= 1
    assert cycle_issues[0].level == IssueLevel.ERROR


def test_disease_without_indicates(valid_bundle: SeedBundle) -> None:
    """Phát hiện bệnh không có bất kỳ triệu chứng INDICATES nào (DISEASE_WITHOUT_INDICATES)."""
    orphan_disease = DiseaseRecord(
        id="ICD10:J98",
        name_en="Respiratory disorder, unspecified",
        name_vi="Rối loạn hô hấp khác",
        category="Hô hấp khác",
        urgency_default=Urgency.MONITOR,
        danger_level=1,
    )
    bundle = valid_bundle.model_copy(update={"diseases": valid_bundle.diseases + [orphan_disease]})

    issues = validate_seed_bundle(bundle)
    orphan_issues = [i for i in issues if i.code == "DISEASE_WITHOUT_INDICATES"]
    assert len(orphan_issues) == 1
    assert orphan_issues[0].level == IssueLevel.ERROR
    assert "ICD10:J98" in orphan_issues[0].message


def test_disease_no_cardinal_symptom_warning(valid_bundle: SeedBundle) -> None:
    """Cảnh báo khi bệnh không có triệu chứng cốt lõi (DISEASE_NO_CARDINAL_SYMPTOM)."""
    # Sửa toàn bộ indicates của ICD10:J18 thành is_cardinal=False
    non_cardinal_edges = [
        e.model_copy(update={"is_cardinal": False}) if e.disease_id == "ICD10:J18" else e
        for e in valid_bundle.indicates
    ]
    bundle = valid_bundle.model_copy(update={"indicates": non_cardinal_edges})

    issues = validate_seed_bundle(bundle)
    cardinal_warnings = [i for i in issues if i.code == "DISEASE_NO_CARDINAL_SYMPTOM"]
    assert len(cardinal_warnings) == 1
    assert cardinal_warnings[0].level == IssueLevel.WARNING
    assert "ICD10:J18" in cardinal_warnings[0].message
