"""Unit tests cho seed_reader.py (F-011).

Kiểm tra:
- Đọc và parse đầy đủ bộ seed hợp lệ vào SeedBundle.
- Hỗ trợ tham số lọc `only`.
- Các hàm tiện ích parse kiểu dữ liệu: boolean, int, float, alias danh sách.
"""

from pathlib import Path

import pytest

from medgraph.graph.seed_reader import (
    _parse_aliases,
    _parse_bool,
    _parse_float,
    _parse_int,
    _parse_str_or_none,
    read_seed,
)

pytestmark = pytest.mark.unit

VALID_SEED_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "seed_mini" / "valid"


def test_parse_helpers() -> None:
    """Kiểm tra các hàm parse giá trị nguyên thủy."""
    assert _parse_bool("true") is True
    assert _parse_bool("1") is True
    assert _parse_bool("yes") is True
    assert _parse_bool("false") is False
    assert _parse_bool("0") is False
    assert _parse_bool("") is False
    assert _parse_bool(None, default=True) is True

    assert _parse_int("123") == 123
    assert _parse_int("") is None
    assert _parse_int(None, default=5) == 5

    assert _parse_float("1.25") == 1.25
    assert _parse_float("") is None
    assert _parse_float(None, default=0.5) == 0.5

    assert _parse_str_or_none("  hello  ") == "hello"
    assert _parse_str_or_none("   ") is None
    assert _parse_str_or_none(None) is None

    assert _parse_aliases("ho khan; ho có đờm ; ") == ["ho khan", "ho có đờm"]
    assert _parse_aliases("") == []


def test_read_seed_valid_bundle() -> None:
    """Đọc toàn bộ thư mục seed hợp lệ thành SeedBundle đầy đủ."""
    bundle = read_seed(VALID_SEED_DIR)

    assert len(bundle.sources) == 3
    assert len(bundle.diseases) == 2
    assert len(bundle.symptoms) == 3
    assert len(bundle.risk_factors) == 1
    assert len(bundle.lab_tests) == 2

    assert len(bundle.indicates) == 3
    assert len(bundle.has_risk_factors) == 1
    assert len(bundle.confirmed_by) == 1
    assert len(bundle.differential_of) == 1
    assert len(bundle.documented_in) == 1
    assert len(bundle.is_a) == 1
    assert len(bundle.superseded_by) == 1

    # Kiểm tra kiểu dữ liệu của record
    doc = bundle.sources[0]
    assert doc.id == "SRC:BYT_2020"
    assert doc.year == 2020

    disease = bundle.diseases[0]
    assert disease.id == "ICD10:J18"
    assert "viêm phổi cộng đồng" in disease.aliases_vi
    assert disease.cant_miss is True


def test_read_seed_with_only_filter() -> None:
    """Kiểm tra lọc chỉ đọc các thực thể được chỉ định qua `only`."""
    bundle = read_seed(VALID_SEED_DIR, only=["sources", "diseases"])

    assert len(bundle.sources) == 3
    assert len(bundle.diseases) == 2
    # Các bảng khác không được nạp
    assert len(bundle.symptoms) == 0
    assert len(bundle.indicates) == 0


def test_read_seed_nonexistent_directory(tmp_path: Path) -> None:
    """Đọc thư mục rỗng trả về SeedBundle với các danh sách rỗng mà không lỗi."""
    bundle = read_seed(tmp_path / "empty_dir")
    assert len(bundle.sources) == 0
    assert len(bundle.diseases) == 0
