"""Hợp nhất alias đã duyệt và đưa chúng vào bản ghi nạp graph."""

import csv
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING, Literal

from pydantic import ValidationError

from medgraph.models.aliases import AliasMergeReport, AliasReviewRow, normalize_alias
from medgraph.models.schemas import ReviewStatus

if TYPE_CHECKING:
    from medgraph.graph.seed_reader import SeedBundle

AliasKind = Literal["symptom", "disease"]
CSV_FIELDS = tuple(AliasReviewRow.model_fields)
FILENAMES: tuple[tuple[AliasKind, str], ...] = (
    ("symptom", "symptoms"),
    ("disease", "diseases"),
)


class AliasMergeError(ValueError):
    """Dữ liệu alias không đủ điều kiện để hợp nhất hoặc nạp vào graph."""


def _read_rows(path: Path) -> list[AliasReviewRow]:
    if not path.exists():
        raise AliasMergeError(f"Missing alias CSV: {path}")
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != CSV_FIELDS:
            raise AliasMergeError(f"Unexpected alias CSV columns: {path}")
        try:
            return [AliasReviewRow.model_validate(row) for row in reader]
        except ValidationError as exc:
            raise AliasMergeError(f"Invalid alias row: {path}") from exc


def _validate_rows(rows: list[AliasReviewRow], kind: AliasKind, bundle: "SeedBundle") -> None:
    entities = bundle.symptoms if kind == "symptom" else bundle.diseases
    entity_ids = {entity.id for entity in entities}
    source_ids = {source.id for source in bundle.sources}
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row.entity_id, row.alias_norm)
        if row.entity_type != kind or row.entity_id not in entity_ids:
            raise AliasMergeError(f"Unknown {kind} entity: {row.entity_id}")
        if row.source_id not in source_ids:
            raise AliasMergeError(f"Unknown source_id: {row.source_id}")
        if not row.alias.strip() or row.alias_norm != normalize_alias(row.alias):
            raise AliasMergeError(f"Invalid alias normalization: {row.entity_id}")
        if key in seen:
            raise AliasMergeError(f"Duplicate alias key: {key}")
        seen.add(key)


def _seed_alias_keys(bundle: "SeedBundle", kind: AliasKind) -> set[tuple[str, str]]:
    entities = bundle.symptoms if kind == "symptom" else bundle.diseases
    return {
        (entity.id, normalize_alias(alias))
        for entity in entities
        if entity.review_status == ReviewStatus.APPROVED
        for alias in entity.aliases_vi
    }


def _write_rows(path: Path, rows: list[AliasReviewRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(row.model_dump() for row in rows)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def merge_aliases(bundle: "SeedBundle", directory: Path) -> AliasMergeReport:
    """Chỉ xuất dòng approved; đếm quyết định và tổng alias duy nhất đã duyệt."""
    exported: dict[AliasKind, list[AliasReviewRow]] = {}
    report = {"approved": 0, "rejected": 0, "pending": 0, "seed_approved": 0, "exported": 0}

    for kind, stem in FILENAMES:
        rows = _read_rows(directory / f"{stem}_draft.csv")
        _validate_rows(rows, kind, bundle)
        seed_keys = _seed_alias_keys(bundle, kind)
        report["seed_approved"] += len(seed_keys)
        canonical = {
            (entity.id, normalize_alias(entity.name_vi))
            for entity in (bundle.symptoms if kind == "symptom" else bundle.diseases)
        }
        known = seed_keys | canonical
        selected = []
        for row in rows:
            report[row.review_status] += 1
            key = (row.entity_id, row.alias_norm)
            if row.review_status == "approved" and key not in known:
                selected.append(row)
        exported[kind] = selected
        report["exported"] += len(selected)

    for kind, stem in FILENAMES:
        _write_rows(directory / f"{stem}.csv", exported[kind])
    report["total_approved"] = report["seed_approved"] + report["exported"]
    return AliasMergeReport.model_validate(report)


def attach_approved_aliases(bundle: "SeedBundle", directory: Path) -> "SeedBundle":
    """Gắn alias từ file chính vào Symptom/Disease; không đọc file nháp."""
    updates = {}
    for kind, stem in FILENAMES:
        path = directory / f"{stem}.csv"
        if not path.exists():
            continue
        rows = _read_rows(path)
        _validate_rows(rows, kind, bundle)
        if any(row.review_status != "approved" for row in rows):
            raise AliasMergeError(f"Unapproved alias in final CSV: {path}")
        entities = bundle.symptoms if kind == "symptom" else bundle.diseases
        extra: dict[str, list[str]] = {}
        for row in rows:
            extra.setdefault(row.entity_id, []).append(row.alias)
        revised = []
        for entity in entities:
            aliases = list(entity.aliases_vi)
            known = {normalize_alias(alias) for alias in (entity.name_vi, *aliases)}
            for alias in extra.get(entity.id, []):
                normalized = normalize_alias(alias)
                if normalized not in known:
                    aliases.append(alias)
                    known.add(normalized)
            revised.append(entity.model_copy(update={"aliases_vi": aliases}))
        updates[f"{stem}"] = revised
    return bundle.model_copy(update=updates) if updates else bundle
