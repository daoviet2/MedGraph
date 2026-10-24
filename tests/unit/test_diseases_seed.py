"""Unit tests kiểm tra danh mục bệnh hô hấp data/seed/diseases.csv (F-009)."""

import csv

import pytest

from medgraph.config import get_settings
from medgraph.graph.seed_reader import read_seed
from medgraph.graph.seed_validator import validate_seed_bundle
from medgraph.models.graph_records import DiseaseRecord
from medgraph.models.schemas import ReviewStatus, Urgency

pytestmark = pytest.mark.unit


def test_diseases_seed_loads_and_parses_properly() -> None:
    """Kiểm tra diseases.csv nạp đầy đủ 30-40 bệnh và parse thành DiseaseRecord."""
    settings = get_settings()
    bundle = read_seed(settings.seed_dir, only=["diseases"])

    assert 30 <= len(bundle.diseases) <= 40, (
        f"Số lượng bệnh phải từ 30 đến 40 dòng, thực tế: {len(bundle.diseases)}"
    )

    for disease in bundle.diseases:
        assert isinstance(disease, DiseaseRecord)
        assert disease.id.startswith("ICD10:") or disease.id.startswith("UMLS:")
        assert disease.name_en and len(disease.name_en.strip()) > 0
        assert disease.name_vi and len(disease.name_vi.strip()) > 0
        assert disease.category and len(disease.category.strip()) > 0
        assert disease.urgency_default in (
            Urgency.EMERGENCY,
            Urgency.SEE_DOCTOR_SOON,
            Urgency.MONITOR,
            Urgency.SELF_CARE_INFO,
        )
        assert disease.danger_level in (1, 2, 3)
        assert isinstance(disease.cant_miss, bool)
        # Quy tắc R3: mọi dòng do agent soạn thảo phải có review_status=pending
        assert disease.review_status == ReviewStatus.PENDING


def test_diseases_seed_csv_columns_and_source_ids() -> None:
    """Kiểm tra cấu trúc cột CSV, tính hợp lệ của source_id và trường notes."""
    settings = get_settings()
    diseases_file = settings.seed_dir / "diseases.csv"
    sources_file = settings.seed_dir / "sources.csv"

    assert diseases_file.exists(), "data/seed/diseases.csv không tồn tại"
    assert sources_file.exists(), "data/seed/sources.csv không tồn tại"

    # Đọc danh sách source_id hợp lệ
    with open(sources_file, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        valid_source_ids = {row["id"].strip() for row in reader if row.get("id")}

    expected_columns = {
        "id",
        "name_en",
        "name_vi",
        "aliases_vi",
        "category",
        "urgency_default",
        "danger_level",
        "cant_miss",
        "source_id",
        "review_status",
        "notes",
    }

    with open(diseases_file, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames is not None
        assert expected_columns.issubset(set(reader.fieldnames)), (
            f"Thiếu cột trong diseases.csv: {expected_columns - set(reader.fieldnames)}"
        )

        rows = list(reader)
        assert 30 <= len(rows) <= 40

        for row in rows:
            disease_id = row["id"].strip()
            source_id = row["source_id"].strip()
            notes = row["notes"].strip()
            review_status = row["review_status"].strip()

            assert source_id in valid_source_ids, (
                f"Bệnh '{disease_id}' có source_id '{source_id}' không tồn tại trong sources.csv"
            )
            assert review_status == "pending", (
                f"Bệnh '{disease_id}' phải có review_status=pending theo quy tắc R3"
            )
            assert len(notes) > 0, (
                f"Bệnh '{disease_id}' phải có notes giải thích lý do gán danger_level"
            )


def test_diseases_seed_cant_miss_and_differentials_coverage() -> None:
    """Kiểm tra danh sách bệnh bắt buộc không bỏ sót (can't-miss) và bệnh ngoài phổi gây ho."""
    settings = get_settings()
    bundle = read_seed(settings.seed_dir, only=["diseases"])
    disease_map = {d.id: d for d in bundle.diseases}

    # Bệnh cấp cứu / can't-miss bắt buộc theo acceptance
    cant_miss_required = [
        "ICD10:I26.9",  # Thuyên tắc phổi
        "ICD10:J93.9",  # Tràn khí màng phổi
        "ICD10:J46",  # Cơn hen phế quản cấp nặng
        "ICD10:J44.1",  # Đợt cấp COPD
        "ICD10:J81",  # Phù phổi cấp
        "ICD10:J80",  # ARDS
        "ICD10:J05.1",  # Viêm nắp thanh quản cấp
        "ICD10:T17.9",  # Dị vật đường thở
        "ICD10:C34.9",  # Ung thư phổi
        "ICD10:J18.9",  # Viêm phổi
    ]
    for req_id in cant_miss_required:
        assert req_id in disease_map, f"Thiếu bệnh can't-miss bắt buộc: {req_id}"
        assert disease_map[req_id].cant_miss is True, (
            f"Bệnh {req_id} ({disease_map[req_id].name_vi}) phải có cant_miss=True"
        )
        assert disease_map[req_id].danger_level in (2, 3), (
            f"Bệnh can't-miss {req_id} phải có danger_level 2 hoặc 3"
        )

    # Bệnh ngoài phổi gây triệu chứng hô hấp (chẩn đoán phân biệt ho/khó thở)
    extra_pulmonary_required = [
        "ICD10:K21.9",  # GERD
        "ICD10:R05.3",  # UACS (Chảy dịch mũi sau)
        "ICD10:T88.7",  # Ho do ACEi
        "ICD10:I50.9",  # Suy tim sung huyết
        "ICD10:F41.0",  # Tăng thông khí do cơn hoảng loạn
    ]
    for ext_id in extra_pulmonary_required:
        assert ext_id in disease_map, f"Thiếu bệnh ngoài phổi phân biệt: {ext_id}"


def test_diseases_seed_passes_validator() -> None:
    """Kiểm tra dữ liệu diseases.csv vượt qua seed_validator không có issue nào."""
    settings = get_settings()
    bundle = read_seed(settings.seed_dir, only=["diseases"])

    issues = validate_seed_bundle(bundle, only=["diseases"])
    assert len(issues) == 0, f"Phát hiện lỗi khi validate diseases: {issues}"
