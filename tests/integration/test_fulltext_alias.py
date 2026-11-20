"""Alias đã duyệt phải tìm được bằng fulltext trên Neo4j thật."""

from pathlib import Path

import pytest
from neo4j import Driver

from medgraph.graph.repository import Neo4jGraphRepository
from medgraph.graph.schema import apply_schema
from medgraph.graph.seed_reader import read_seed

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = (
    ("tức ngực", "HP:0100749"),
    ("khạc ra máu", "HP:0002105"),
    ("thở dốc", "HP:0002094"),
)


@pytest.mark.integration
def test_fulltext_finds_approved_vietnamese_aliases(driver: Driver) -> None:
    bundle = read_seed(
        ROOT / "data" / "seed",
        aliases_dir=ROOT / "data" / "aliases_vi",
    )
    ids = {entity_id for _, entity_id in SAMPLES}
    selected = [symptom for symptom in bundle.symptoms if symptom.id in ids]
    assert len(selected) == len(ids)
    for phrase, expected_id in SAMPLES:
        assert phrase in next(item for item in selected if item.id == expected_id).aliases_vi
    apply_schema(driver)
    repository = Neo4jGraphRepository(driver)

    with driver.session() as session:
        transaction = session.begin_transaction()
        try:
            repository.upsert_symptoms(selected, tx=transaction)
            for phrase, expected_id in SAMPLES:
                assert repository.search_symptom_alias(phrase, tx=transaction)[0] == expected_id
        finally:
            transaction.rollback()
