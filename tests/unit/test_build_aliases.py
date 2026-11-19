"""Alias nháp: chống trùng, giữ dòng đã rà, kiểm tra nguồn và không gọi mạng."""

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from medgraph.llm.alias_builder import (
    CSV_FIELDS,
    AliasBuildError,
    AliasDraftGenerator,
    read_entities,
)
from medgraph.llm.cache import CachedLLMClient
from medgraph.llm.prompts import PromptRegistry
from medgraph.llm.providers.fake import FakeLLMClient
from medgraph.models.aliases import normalize_alias


def _seed(root: Path) -> Path:
    seed = root / "seed"
    seed.mkdir()
    (seed / "sources.csv").write_text("id\nSRC:TEST\n", encoding="utf-8")
    (seed / "symptoms.csv").write_text(
        'id,name_vi,aliases_vi,source_id\nHP:1,Khò khè,"thở khò khè;tiếng rít",SRC:TEST\n',
        encoding="utf-8",
    )
    (seed / "diseases.csv").write_text(
        "id,name_vi,aliases_vi,source_id\nICD:1,Viêm phổi,sưng phổi,SRC:TEST\n",
        encoding="utf-8",
    )
    return seed


def _response(*pairs: tuple[str, str]) -> str:
    return json.dumps(
        {"aliases": [{"entity_id": entity_id, "alias": alias} for entity_id, alias in pairs]},
        ensure_ascii=False,
    )


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _generator(client: FakeLLMClient | CachedLLMClient, batch_size: int = 8) -> AliasDraftGenerator:
    return AliasDraftGenerator(
        client,
        PromptRegistry(Path("prompts")).get("build_aliases", "v1"),
        batch_size=batch_size,
        clock=lambda: datetime(2026, 11, 19, tzinfo=UTC),
    )


@pytest.mark.unit
def test_generate_is_idempotent_and_filters_canonical_aliases(tmp_path: Path) -> None:
    entities = read_entities(_seed(tmp_path))
    fake = FakeLLMClient(
        [
            _response(
                ("HP:1", "kho khe"),
                ("HP:1", "thở rít nhẹ"),
                ("HP:1", "Thở rít nhẹ"),
                ("ICD:1", "Sưng phổi"),
                ("ICD:1", "phổi bị viêm"),
            )
        ]
    )
    client = CachedLLMClient(fake, tmp_path / "cache")
    generator = _generator(client)
    output = tmp_path / "aliases"

    first = generator.generate(entities, output)
    symptom_rows = _rows(output / "symptoms_draft.csv")
    disease_rows = _rows(output / "diseases_draft.csv")
    assert first.entities_processed == 2
    assert first.aliases_proposed == 5
    assert first.aliases_added == 2
    assert len(symptom_rows) == len(disease_rows) == 1
    assert symptom_rows[0]["alias_norm"] == "tho rit nhe"
    assert disease_rows[0]["alias"] == "phổi bị viêm"
    for row in symptom_rows + disease_rows:
        assert row["source_id"] == "SRC:TEST"
        assert row["provenance"] == "auto_extracted"
        assert row["review_status"] == "pending"
        assert row["model"] == "fake-small"
        assert row["prompt_version"] == "v1"
        assert row["generated_at"] == "2026-11-19T00:00:00+00:00"

    before = {path: path.read_bytes() for path in output.glob("*.csv")}
    second = generator.generate(entities, output)
    assert second.aliases_added == 0
    assert fake.call_count == 1
    assert {path: path.read_bytes() for path in output.glob("*.csv")} == before


@pytest.mark.unit
def test_existing_approved_and_rejected_rows_are_preserved(tmp_path: Path) -> None:
    entities = read_entities(_seed(tmp_path), entity_type="symptom")
    output = tmp_path / "aliases"
    output.mkdir()
    path = output / "symptoms_draft.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        for alias, status in (("thở gấp", "approved"), ("khò khè nặng", "rejected")):
            writer.writerow(
                {
                    "entity_id": "HP:1",
                    "entity_type": "symptom",
                    "alias": alias,
                    "alias_norm": normalize_alias(alias),
                    "model": "old-model",
                    "prompt_version": "v0",
                    "generated_at": "2026-01-01T00:00:00+00:00",
                    "review_status": status,
                    "reviewer_note": "human decision",
                    "source_id": "SRC:TEST",
                    "provenance": "auto_extracted",
                }
            )
    existing_bytes = path.read_bytes()
    fake = FakeLLMClient(
        [_response(("HP:1", "thở gấp"), ("HP:1", "khò khè nặng"), ("HP:1", "thở khụt khịt"))]
    )

    report = _generator(fake).generate(entities, output)
    assert report.aliases_added == 1
    assert path.read_bytes().startswith(existing_bytes)
    rows = _rows(path)
    assert [row["review_status"] for row in rows] == ["approved", "rejected", "pending"]
    assert [row["reviewer_note"] for row in rows[:2]] == ["human decision"] * 2


@pytest.mark.unit
def test_unknown_llm_entity_aborts_without_writing(tmp_path: Path) -> None:
    entities = read_entities(_seed(tmp_path))
    fake = FakeLLMClient([_response(("HP:1", "thở rít nhẹ")), _response(("OTHER", "x"))])
    output = tmp_path / "aliases"
    with pytest.raises(AliasBuildError, match="unknown entity_id"):
        _generator(fake, batch_size=1).generate(entities, output)
    assert not output.exists()


@pytest.mark.unit
def test_read_entities_checks_source_and_limit(tmp_path: Path) -> None:
    seed = _seed(tmp_path)
    assert len(read_entities(seed, limit=1)) == 1
    assert read_entities(seed, entity_type="disease")[0].entity_id == "ICD:1"
    assert normalize_alias(" Đờm  ĐẶC ") == "dom dac"
    with pytest.raises(AliasBuildError, match="limit must be positive"):
        read_entities(seed, limit=0)
    (seed / "sources.csv").write_text("id\nSRC:OTHER\n", encoding="utf-8")
    with pytest.raises(AliasBuildError, match="Unknown source_id"):
        read_entities(seed)
