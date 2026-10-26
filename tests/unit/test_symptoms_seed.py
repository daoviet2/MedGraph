"""Unit tests kiểm tra danh mục triệu chứng, yếu tố nguy cơ, xét nghiệm và IS_A (F-010)."""

import csv

import pytest

from medgraph.config import get_settings
from medgraph.graph.seed_reader import read_seed
from medgraph.graph.seed_validator import find_directed_cycles, validate_seed_bundle
from medgraph.models.graph_records import (
    IsAEdge,
    LabTestRecord,
    RiskFactorRecord,
    SymptomRecord,
)
from medgraph.models.schemas import Provenance, ReviewStatus

pytestmark = pytest.mark.unit


def test_symptoms_seed_loads_and_parses_properly() -> None:
    """Kiểm tra symptoms.csv nạp đầy đủ các SymptomRecord với mã HPO chuẩn."""
    settings = get_settings()
    bundle = read_seed(settings.seed_dir, only=["symptoms"])

    assert len(bundle.symptoms) >= 50, (
        f"Số lượng triệu chứng phải >= 50, thực tế: {len(bundle.symptoms)}"
    )

    for symptom in bundle.symptoms:
        assert isinstance(symptom, SymptomRecord)
        assert symptom.id.startswith("HP:") or symptom.id.startswith("UMLS:")
        assert symptom.name_en and len(symptom.name_en.strip()) > 0
        assert symptom.name_vi and len(symptom.name_vi.strip()) > 0
        assert isinstance(symptom.is_red_flag, bool)
        assert symptom.review_status == ReviewStatus.PENDING

    # Kiểm tra các triệu chứng red flag hô hấp bắt buộc
    red_flags = {s.id: s for s in bundle.symptoms if s.is_red_flag}
    assert len(red_flags) >= 8, f"Cần ít nhất 8 triệu chứng red flag, thực tế: {len(red_flags)}"

    # Kiểm tra các red flag cụ thể theo acceptance
    assert "HP:0002105" in red_flags, "Thiếu red flag Ho ra máu (HP:0002105)"
    assert "HP:0025440" in red_flags, "Thiếu red flag Khó thở khi nghỉ (HP:0025440)"
    assert "HP:0000961" in red_flags, "Thiếu red flag Tím tái (HP:0000961)"
    assert "HP:0010307" in red_flags, "Thiếu red flag Thở rít thanh quản (HP:0010307)"
    assert "HP:0031250" in red_flags, "Thiếu red flag Đờm bọt hồng phù phổi cấp (HP:0031250)"
    assert "HP:0002102" in red_flags, "Thiếu red flag Co kéo cơ hô hấp phụ (HP:0002102)"


def test_risk_factors_seed_loads_and_parses_properly() -> None:
    """Kiểm tra risk_factors.csv nạp đầy đủ các RiskFactorRecord với mã RF:."""
    settings = get_settings()
    bundle = read_seed(settings.seed_dir, only=["risk_factors"])

    assert len(bundle.risk_factors) >= 12, (
        f"Số lượng yếu tố nguy cơ phải >= 12, thực tế: {len(bundle.risk_factors)}"
    )

    rf_ids = {rf.id for rf in bundle.risk_factors}
    assert "RF:smoking" in rf_ids, "Thiếu yếu tố nguy cơ hút thuốc lá"
    assert "RF:tb_contact" in rf_ids, "Thiếu yếu tố nguy cơ tiếp xúc lao"
    assert "RF:elderly" in rf_ids, "Thiếu yếu tố nguy cơ người cao tuổi"

    for rf in bundle.risk_factors:
        assert isinstance(rf, RiskFactorRecord)
        assert rf.id.startswith("RF:")
        assert rf.name_vi and len(rf.name_vi.strip()) > 0
        assert rf.type and len(rf.type.strip()) > 0
        assert rf.review_status == ReviewStatus.PENDING


def test_total_symptoms_and_risk_factors_count() -> None:
    """Kiểm tra tiêu chí acceptance: tổng symptoms + risk_factors từ 60 đến 100 dòng."""
    settings = get_settings()
    bundle = read_seed(settings.seed_dir, only=["symptoms", "risk_factors"])

    total = len(bundle.symptoms) + len(bundle.risk_factors)
    assert 60 <= total <= 100, (
        f"Tổng symptoms + risk_factors phải từ 60 đến 100, thực tế: {total} "
        f"({len(bundle.symptoms)} symptoms + {len(bundle.risk_factors)} risk factors)"
    )


def test_lab_tests_seed_loads_and_parses_properly() -> None:
    """Kiểm tra lab_tests.csv nạp đầy đủ >= 15 xét nghiệm cận lâm sàng hô hấp."""
    settings = get_settings()
    bundle = read_seed(settings.seed_dir, only=["lab_tests"])

    assert len(bundle.lab_tests) >= 15, (
        f"Số lượng xét nghiệm phải >= 15, thực tế: {len(bundle.lab_tests)}"
    )

    test_ids = {lab.id for lab in bundle.lab_tests}
    # Kiểm tra các xét nghiệm trọng yếu
    assert "LOINC:1988-5" in test_ids, "Thiếu xét nghiệm CRP"
    assert "LOINC:48065-7" in test_ids, "Thiếu xét nghiệm D-dimer"
    assert "LOINC:2019-8" in test_ids, "Thiếu xét nghiệm Khí máu động mạch"
    assert "LAB:xray_chest" in test_ids, "Thiếu Chụp X-quang ngực thẳng"
    assert "LAB:ctpa" in test_ids, "Thiếu Chụp CT mạch máu phổi"
    assert "LAB:spirometry" in test_ids, "Thiếu Đo chức năng thông khí phổi"

    for lab in bundle.lab_tests:
        assert isinstance(lab, LabTestRecord)
        assert lab.id.startswith("LOINC:") or lab.id.startswith("LAB:")
        assert lab.name_vi and len(lab.name_vi.strip()) > 0
        assert lab.purpose and len(lab.purpose.strip()) > 0
        assert lab.review_status == ReviewStatus.PENDING


def test_is_a_edges_validity_and_acyclic() -> None:
    """Kiểm tra quan hệ phân cấp triệu chứng is_a.csv không có chu trình và ID hợp lệ."""
    settings = get_settings()
    bundle = read_seed(settings.seed_dir, only=["symptoms", "is_a"])

    symptom_ids = {s.id for s in bundle.symptoms}

    assert len(bundle.is_a) >= 15, f"Số lượng quan hệ is_a phải >= 15, thực tế: {len(bundle.is_a)}"

    pairs: list[tuple[str, str]] = []
    for edge in bundle.is_a:
        assert isinstance(edge, IsAEdge)
        assert edge.child_id in symptom_ids, f"child_id '{edge.child_id}' không có trong symptoms"
        assert edge.parent_id in symptom_ids, (
            f"parent_id '{edge.parent_id}' không có trong symptoms"
        )
        assert edge.child_id != edge.parent_id, (
            f"Tự liên kết vòng trên triệu chứng '{edge.child_id}'"
        )
        assert edge.source_id.startswith("SRC:")
        assert edge.provenance == Provenance.CURATED
        assert edge.confidence == 1.0
        assert edge.evidence_count >= 1
        pairs.append((edge.child_id, edge.parent_id))

    cycles = find_directed_cycles(pairs)
    assert len(cycles) == 0, f"Phát hiện chu trình trong quan hệ IS_A: {cycles}"


def test_validator_passes_all_f010_entities() -> None:
    """Kiểm tra toàn bộ dữ liệu F-010 vượt qua seed_validator không có lỗi hay cảnh báo."""
    settings = get_settings()
    bundle = read_seed(
        settings.seed_dir,
        only=["sources", "symptoms", "risk_factors", "lab_tests", "is_a"],
    )

    issues = validate_seed_bundle(
        bundle,
        only=["sources", "symptoms", "risk_factors", "lab_tests", "is_a"],
    )
    assert len(issues) == 0, f"Phát hiện lỗi khi validate dữ liệu F-010: {issues}"


def test_source_ids_exist_in_sources_csv() -> None:
    """Kiểm tra mọi source_id trong F-010 đều tồn tại trong sources.csv."""
    settings = get_settings()
    sources_file = settings.seed_dir / "sources.csv"
    with open(sources_file, encoding="utf-8") as f:
        valid_sources = {row["id"].strip() for row in csv.DictReader(f) if row.get("id")}

    for name in ["symptoms.csv", "risk_factors.csv", "lab_tests.csv", "edges/is_a.csv"]:
        file_path = settings.seed_dir / name
        assert file_path.exists(), f"File {name} không tồn tại"
        with open(file_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                src_id = row.get("source_id", "").strip()
                assert src_id in valid_sources, (
                    f"source_id '{src_id}' trong {name} không tồn tại trong sources.csv"
                )
