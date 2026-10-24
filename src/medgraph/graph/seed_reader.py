"""Trình nạp dữ liệu seed từ file CSV thành các bản ghi đồ thị Pydantic (SeedBundle).

Không phụ thuộc và không kết nối Neo4j.
Đọc các file CSV từ data/seed/ và data/seed/edges/ với encoding utf-8.
"""

import csv
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from medgraph.models.graph_records import (
    ConfirmedByEdge,
    DifferentialOfEdge,
    DiseaseRecord,
    DocumentedInEdge,
    HasRiskFactorEdge,
    IndicatesEdge,
    IsAEdge,
    LabTestRecord,
    RiskFactorRecord,
    SourceDocRecord,
    SupersededByEdge,
    SymptomRecord,
)


def _parse_bool(val: Any, default: bool = False) -> bool:
    """Chuyển đổi chuỗi sang boolean an toàn."""
    if val is None or val == "":
        return default
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    return s in ("true", "1", "yes", "t")


def _parse_int(val: Any, default: int | None = None) -> int | None:
    """Chuyển đổi chuỗi sang số nguyên an toàn."""
    if val is None or str(val).strip() == "":
        return default
    return int(str(val).strip())


def _parse_float(val: Any, default: float | None = None) -> float | None:
    """Chuyển đổi chuỗi sang số thực an toàn."""
    if val is None or str(val).strip() == "":
        return default
    return float(str(val).strip())


def _parse_str_or_none(val: Any) -> str | None:
    """Chuyển chuỗi rỗng thành None."""
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def _parse_aliases(val: Any) -> list[str]:
    """Phân tách chuỗi danh sách alias tiếng Việt theo dấu chấm phẩy (;)."""
    if not val:
        return []
    return [item.strip() for item in str(val).split(";") if item.strip()]


class SeedBundle(BaseModel):
    """Gói toàn bộ bản ghi thực thể và quan hệ nạp từ thư mục dữ liệu seed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sources: list[SourceDocRecord] = Field(default_factory=list)
    diseases: list[DiseaseRecord] = Field(default_factory=list)
    symptoms: list[SymptomRecord] = Field(default_factory=list)
    risk_factors: list[RiskFactorRecord] = Field(default_factory=list)
    lab_tests: list[LabTestRecord] = Field(default_factory=list)

    indicates: list[IndicatesEdge] = Field(default_factory=list)
    has_risk_factors: list[HasRiskFactorEdge] = Field(default_factory=list)
    confirmed_by: list[ConfirmedByEdge] = Field(default_factory=list)
    differential_of: list[DifferentialOfEdge] = Field(default_factory=list)
    documented_in: list[DocumentedInEdge] = Field(default_factory=list)
    is_a: list[IsAEdge] = Field(default_factory=list)
    superseded_by: list[SupersededByEdge] = Field(default_factory=list)


def _read_csv_rows(file_path: Path) -> list[dict[str, str]]:
    """Đọc file CSV trả về danh sách dict."""
    if not file_path.exists():
        return []
    with file_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [row for row in reader if any(v.strip() for v in row.values() if v)]


def _row_to_source_doc(row: dict[str, str]) -> SourceDocRecord:
    kwargs: dict[str, Any] = {
        "id": row.get("id"),
        "title": row.get("title"),
        "publisher": row.get("publisher"),
        "year": _parse_int(row.get("year")),
        "url": row.get("url"),
        "license": row.get("license"),
        "effective_from": row.get("effective_from"),
        "effective_to": _parse_str_or_none(row.get("effective_to")),
        "status": row.get("status"),
        "superseded_by": _parse_str_or_none(row.get("superseded_by")),
    }
    if "review_status" in row and row["review_status"].strip():
        kwargs["review_status"] = row["review_status"].strip()
    return SourceDocRecord(**kwargs)


def _row_to_disease(row: dict[str, str]) -> DiseaseRecord:
    kwargs: dict[str, Any] = {
        "id": row.get("id"),
        "name_en": row.get("name_en"),
        "name_vi": row.get("name_vi"),
        "aliases_vi": _parse_aliases(row.get("aliases_vi")),
        "category": row.get("category"),
        "urgency_default": row.get("urgency_default"),
        "danger_level": _parse_int(row.get("danger_level")),
        "cant_miss": _parse_bool(row.get("cant_miss"), default=False),
    }
    if "review_status" in row and row["review_status"].strip():
        kwargs["review_status"] = row["review_status"].strip()
    return DiseaseRecord(**kwargs)


def _row_to_symptom(row: dict[str, str]) -> SymptomRecord:
    kwargs: dict[str, Any] = {
        "id": row.get("id"),
        "name_en": row.get("name_en"),
        "name_vi": row.get("name_vi"),
        "aliases_vi": _parse_aliases(row.get("aliases_vi")),
        "is_red_flag": _parse_bool(row.get("is_red_flag"), default=False),
    }
    if "review_status" in row and row["review_status"].strip():
        kwargs["review_status"] = row["review_status"].strip()
    return SymptomRecord(**kwargs)


def _row_to_risk_factor(row: dict[str, str]) -> RiskFactorRecord:
    kwargs: dict[str, Any] = {
        "id": row.get("id"),
        "name_vi": row.get("name_vi"),
        "type": row.get("type"),
    }
    if "review_status" in row and row["review_status"].strip():
        kwargs["review_status"] = row["review_status"].strip()
    return RiskFactorRecord(**kwargs)


def _row_to_lab_test(row: dict[str, str]) -> LabTestRecord:
    kwargs: dict[str, Any] = {
        "id": row.get("id"),
        "name_vi": row.get("name_vi"),
        "purpose": row.get("purpose"),
    }
    if "review_status" in row and row["review_status"].strip():
        kwargs["review_status"] = row["review_status"].strip()
    return LabTestRecord(**kwargs)


def _populate_common_edge_kwargs(row: dict[str, str], kwargs: dict[str, Any]) -> None:
    if "source_id" in row and row["source_id"].strip():
        kwargs["source_id"] = row["source_id"].strip()
    if "provenance" in row and row["provenance"].strip():
        kwargs["provenance"] = row["provenance"].strip()
    if "evidence_count" in row and row["evidence_count"].strip():
        kwargs["evidence_count"] = _parse_int(row["evidence_count"])
    if "confidence" in row and row["confidence"].strip():
        kwargs["confidence"] = _parse_float(row["confidence"])


def _row_to_indicates(row: dict[str, str]) -> IndicatesEdge:
    kwargs: dict[str, Any] = {
        "symptom_id": row.get("symptom_id"),
        "disease_id": row.get("disease_id"),
        "is_cardinal": _parse_bool(row.get("is_cardinal"), default=False),
    }
    if "weight" in row and row["weight"].strip():
        kwargs["weight"] = _parse_float(row["weight"])
    _populate_common_edge_kwargs(row, kwargs)
    return IndicatesEdge(**kwargs)


def _row_to_has_risk_factor(row: dict[str, str]) -> HasRiskFactorEdge:
    kwargs: dict[str, Any] = {
        "disease_id": row.get("disease_id"),
        "risk_id": row.get("risk_id"),
    }
    if "weight" in row and row["weight"].strip():
        kwargs["weight"] = _parse_float(row["weight"])
    _populate_common_edge_kwargs(row, kwargs)
    return HasRiskFactorEdge(**kwargs)


def _row_to_confirmed_by(row: dict[str, str]) -> ConfirmedByEdge:
    kwargs: dict[str, Any] = {
        "disease_id": row.get("disease_id"),
        "lab_id": row.get("lab_id"),
        "role": row.get("role"),
    }
    _populate_common_edge_kwargs(row, kwargs)
    return ConfirmedByEdge(**kwargs)


def _row_to_differential_of(row: dict[str, str]) -> DifferentialOfEdge:
    kwargs: dict[str, Any] = {
        "disease_id": row.get("disease_id"),
        "other_id": row.get("other_id"),
        "distinguishing_features": row.get("distinguishing_features"),
    }
    _populate_common_edge_kwargs(row, kwargs)
    return DifferentialOfEdge(**kwargs)


def _row_to_documented_in(row: dict[str, str]) -> DocumentedInEdge:
    kwargs: dict[str, Any] = {
        "disease_id": row.get("disease_id"),
        "source_doc_id": row.get("source_doc_id"),
        "section": row.get("section"),
    }
    _populate_common_edge_kwargs(row, kwargs)
    return DocumentedInEdge(**kwargs)


def _row_to_is_a(row: dict[str, str]) -> IsAEdge:
    kwargs: dict[str, Any] = {
        "child_id": row.get("child_id"),
        "parent_id": row.get("parent_id"),
    }
    _populate_common_edge_kwargs(row, kwargs)
    return IsAEdge(**kwargs)


def _row_to_superseded_by(row: dict[str, str]) -> SupersededByEdge:
    kwargs: dict[str, Any] = {
        "old_id": row.get("old_id"),
        "new_id": row.get("new_id"),
        "effective_from": row.get("effective_from"),
    }
    _populate_common_edge_kwargs(row, kwargs)
    return SupersededByEdge(**kwargs)


def read_seed(seed_dir: Path | str, only: list[str] | None = None) -> SeedBundle:
    """Đọc dữ liệu seed từ thư mục và nạp vào SeedBundle.

    Args:
        seed_dir: Thư mục chứa dữ liệu seed.
        only: Danh sách các loại thực thể/quan hệ cần đọc (ví dụ: ['sources', 'diseases']).
              Nếu None, đọc toàn bộ.

    Returns:
        Đối tượng SeedBundle chứa danh sách các bản ghi.
    """
    root = Path(seed_dir)
    edges_dir = root / "edges"
    filter_set = set(only) if only is not None else None

    def should_load(key: str) -> bool:
        return filter_set is None or key in filter_set

    bundle_dict: dict[str, list[Any]] = {
        "sources": [],
        "diseases": [],
        "symptoms": [],
        "risk_factors": [],
        "lab_tests": [],
        "indicates": [],
        "has_risk_factors": [],
        "confirmed_by": [],
        "differential_of": [],
        "documented_in": [],
        "is_a": [],
        "superseded_by": [],
    }

    parsers: list[tuple[str, Path, Callable[[dict[str, str]], Any]]] = [
        ("sources", root / "sources.csv", _row_to_source_doc),
        ("diseases", root / "diseases.csv", _row_to_disease),
        ("symptoms", root / "symptoms.csv", _row_to_symptom),
        ("risk_factors", root / "risk_factors.csv", _row_to_risk_factor),
        ("lab_tests", root / "lab_tests.csv", _row_to_lab_test),
        ("indicates", edges_dir / "indicates.csv", _row_to_indicates),
        ("has_risk_factors", edges_dir / "has_risk_factor.csv", _row_to_has_risk_factor),
        ("confirmed_by", edges_dir / "confirmed_by.csv", _row_to_confirmed_by),
        ("differential_of", edges_dir / "differential_of.csv", _row_to_differential_of),
        ("documented_in", edges_dir / "documented_in.csv", _row_to_documented_in),
        ("is_a", edges_dir / "is_a.csv", _row_to_is_a),
        ("superseded_by", edges_dir / "superseded_by.csv", _row_to_superseded_by),
    ]

    for key, path, parser in parsers:
        if should_load(key) and path.exists():
            rows = _read_csv_rows(path)
            bundle_dict[key] = [parser(r) for r in rows]

    return SeedBundle(**bundle_dict)
