"""Kiểm tra hợp nhất quyết định rà soát và nạp alias mà không cần Neo4j."""

import csv
from pathlib import Path

import pytest

from medgraph.graph.alias_catalog import AliasMergeError, attach_approved_aliases, merge_aliases
from medgraph.graph.seed_reader import read_seed
from medgraph.models.aliases import AliasReviewRow, normalize_alias

SEED = Path(__file__).resolve().parents[1] / "fixtures" / "seed_mini" / "valid"
FIELDS = tuple(AliasReviewRow.model_fields)


def _draft(path: Path, *items: tuple[str, str, str, str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        for entity_id, kind, alias, status in items:
            writer.writerow(
                AliasReviewRow(
                    entity_id=entity_id,
                    entity_type=kind,
                    alias=alias,
                    alias_norm=normalize_alias(alias),
                    model="DeepSeek-V4-Flash",
                    prompt_version="v1",
                    generated_at="2026-11-19T00:00:00+00:00",
                    review_status=status,
                    reviewer_note="Reviewed by user" if status != "pending" else "",
                    source_id="SRC:WHO_2022",
                ).model_dump()
            )


@pytest.mark.unit
def test_merge_only_approved_and_overlay_is_idempotent(tmp_path: Path) -> None:
    bundle = read_seed(SEED, only=["sources", "symptoms", "diseases"])
    _draft(
        tmp_path / "symptoms_draft.csv",
        ("HP:0002094", "symptom", "thở dốc", "approved"),
        ("HP:0002094", "symptom", "thở ngắn", "rejected"),
        ("HP:0012735", "symptom", "ho khù khụ", "pending"),
    )
    _draft(
        tmp_path / "diseases_draft.csv",
        ("ICD10:J18", "disease", "phổi bị viêm", "approved"),
    )

    report = merge_aliases(bundle, tmp_path)
    assert (report.approved, report.rejected, report.pending, report.exported) == (2, 1, 1, 2)
    assert report.total_approved == report.seed_approved + 2
    final = tmp_path / "symptoms.csv"
    with final.open(encoding="utf-8", newline="") as stream:
        assert [row["alias"] for row in csv.DictReader(stream)] == ["thở dốc"]

    merged = attach_approved_aliases(bundle, tmp_path)
    symptom = next(item for item in merged.symptoms if item.id == "HP:0002094")
    assert symptom.aliases_vi == ["hụt hơi", "thở gấp", "thở dốc"]
    assert (
        "thở dốc"
        not in next(item for item in bundle.symptoms if item.id == "HP:0002094").aliases_vi
    )
    assert attach_approved_aliases(merged, tmp_path).symptoms == merged.symptoms

    before = {path.name: path.read_bytes() for path in tmp_path.glob("*.csv")}
    assert merge_aliases(bundle, tmp_path) == report
    assert {path.name: path.read_bytes() for path in tmp_path.glob("*.csv")} == before


@pytest.mark.unit
def test_merge_rejects_bad_source_before_writing(tmp_path: Path) -> None:
    bundle = read_seed(SEED, only=["sources", "symptoms", "diseases"])
    _draft(tmp_path / "symptoms_draft.csv", ("HP:0002094", "symptom", "thở dốc", "approved"))
    _draft(tmp_path / "diseases_draft.csv")
    path = tmp_path / "symptoms_draft.csv"
    path.write_text(
        path.read_text(encoding="utf-8").replace("SRC:WHO_2022", "SRC:UNKNOWN"), encoding="utf-8"
    )

    with pytest.raises(AliasMergeError, match="Unknown source_id"):
        merge_aliases(bundle, tmp_path)
    assert not (tmp_path / "symptoms.csv").exists()
    assert not (tmp_path / "diseases.csv").exists()


@pytest.mark.unit
def test_final_csv_refuses_pending_alias(tmp_path: Path) -> None:
    bundle = read_seed(SEED, only=["sources", "symptoms", "diseases"])
    _draft(tmp_path / "symptoms.csv", ("HP:0002094", "symptom", "thở dốc", "pending"))
    with pytest.raises(AliasMergeError, match="Unapproved alias"):
        attach_approved_aliases(bundle, tmp_path)
