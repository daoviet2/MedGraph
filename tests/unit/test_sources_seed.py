"""Unit test kiểm tra tính hợp lệ của nguồn dữ liệu sources.csv (F-008)."""

from pathlib import Path

import pytest

from medgraph.config import get_settings
from medgraph.graph.seed_reader import read_seed
from medgraph.graph.seed_validator import validate_seed_bundle
from medgraph.models.graph_records import SourceDocRecord
from medgraph.models.schemas import ReviewStatus

pytestmark = pytest.mark.unit


def test_sources_seed_loads_and_parses_properly() -> None:
    """Kiểm tra sources.csv trong data/seed parse thành các SourceDocRecord hợp lệ."""
    settings = get_settings()
    bundle = read_seed(settings.seed_dir, only=["sources"])

    assert len(bundle.sources) >= 5, "sources.csv phải có ít nhất 5 nguồn tài liệu"

    source_ids = {s.id for s in bundle.sources}
    assert "SRC:HPO" in source_ids, "Thiếu nguồn HPO"
    assert "SRC:MEDLINEPLUS" in source_ids, "Thiếu nguồn MedlinePlus"
    assert "SRC:BYT_PNEUMONIA_2020" in source_ids or "SRC:BYT_COPD_2023" in source_ids, (
        "Thiếu guideline hô hấp của Bộ Y tế Việt Nam"
    )
    assert "SRC:MANUAL_CURATION" in source_ids, "Thiếu nguồn SRC:MANUAL_CURATION"

    # Toàn bộ bản ghi là SourceDocRecord và review_status=pending theo quy tắc R3
    for source in bundle.sources:
        assert isinstance(source, SourceDocRecord)
        assert source.id.startswith("SRC:")
        assert source.review_status in (ReviewStatus.PENDING, ReviewStatus.APPROVED)
        assert source.year >= 1900


def test_sources_seed_passes_validation() -> None:
    """Kiểm tra sources.csv vượt qua kiểm tra toàn vẹn không có issue lỗi."""
    settings = get_settings()
    bundle = read_seed(settings.seed_dir, only=["sources"])

    issues = validate_seed_bundle(bundle, only=["sources"])
    assert len(issues) == 0, f"Phát hiện lỗi trong sources.csv: {issues}"


def test_sources_lifecycle_and_superseded_consistency() -> None:
    """Kiểm tra tính nhất quán vòng đời cho tài liệu bị thay thế (superseded)."""
    settings = get_settings()
    bundle = read_seed(settings.seed_dir, only=["sources"])

    sources_map = {s.id: s for s in bundle.sources}
    superseded_source = sources_map.get("SRC:BYT_COPD_2018")
    assert superseded_source is not None
    assert superseded_source.status == "superseded"
    assert superseded_source.superseded_by == "SRC:BYT_COPD_2023"
    assert superseded_source.effective_to is not None

    new_source = sources_map.get("SRC:BYT_COPD_2023")
    assert new_source is not None
    assert new_source.status == "active"
    assert str(superseded_source.effective_to) <= str(new_source.effective_from)


def test_docs_05_exists_and_contains_required_sources() -> None:
    """Kiểm tra file tài liệu docs/05_Nguon_du_lieu_va_license.md đầy đủ nội dung."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    docs_05 = repo_root / "docs" / "05_Nguon_du_lieu_va_license.md"

    assert docs_05.exists(), "docs/05_Nguon_du_lieu_va_license.md không tồn tại"
    content = docs_05.read_text(encoding="utf-8")

    assert "SRC:HPO" in content
    assert "SRC:MEDLINEPLUS" in content
    assert "SRC:BYT_PNEUMONIA_2020" in content
    assert "SRC:MANUAL_CURATION" in content
    assert "ODC-BY" in content
    assert "Public Domain" in content
