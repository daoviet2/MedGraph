"""Kiểm tra IDF được ghi vào Neo4j và ổn định khi tính lại."""

from pathlib import Path
from uuid import uuid4

import pytest
from neo4j import Driver

from medgraph.graph.repository import Neo4jGraphRepository
from medgraph.graph.seed_reader import read_seed
from medgraph.graph.stats import refresh_symptom_idf

SEED_MINI_VALID = Path(__file__).resolve().parents[1] / "fixtures" / "seed_mini" / "valid"


@pytest.mark.integration
def test_idf_written_for_every_connected_test_symptom(driver: Driver) -> None:
    """Dùng ID riêng và dọn fixture để không ảnh hưởng graph có sẵn."""
    bundle = read_seed(SEED_MINI_VALID)
    suffix = uuid4().hex
    disease_ids = [f"UMLS:TEST_D_{suffix}_{index}" for index in range(2)]
    symptom_ids = [f"UMLS:TEST_S_{suffix}_{index}" for index in range(2)]
    source_id = "SRC:MANUAL_CURATION"
    diseases = [
        bundle.diseases[index].model_copy(update={"id": disease_ids[index], "source_id": source_id})
        for index in range(2)
    ]
    symptoms = [
        bundle.symptoms[index].model_copy(update={"id": symptom_ids[index], "source_id": source_id})
        for index in range(2)
    ]
    edge_template = bundle.indicates[0]
    edges = [
        edge_template.model_copy(
            update={
                "symptom_id": symptom_ids[s],
                "disease_id": disease_ids[d],
                "source_id": source_id,
            }
        )
        for s, d in ((0, 0), (1, 0), (1, 1))
    ]
    repo = Neo4jGraphRepository(driver, batch_size=2)

    with driver.session() as session:
        tx = session.begin_transaction()
        try:
            repo.upsert_diseases(diseases, tx=tx)
            repo.upsert_symptoms(symptoms, tx=tx)
            repo.upsert_indicates_edges(edges, tx=tx)

            assert refresh_symptom_idf(repo, tx=tx) >= 2
            first = {
                record["id"]: record["idf"]
                for record in tx.run(
                    "MATCH (s:Symptom) WHERE s.id IN $ids RETURN s.id AS id, s.idf AS idf",
                    ids=symptom_ids,
                )
            }
            assert set(first) == set(symptom_ids)
            assert all(value is not None for value in first.values())
            assert first[symptom_ids[0]] > first[symptom_ids[1]]

            assert refresh_symptom_idf(repo, tx=tx) >= 2
            second = {
                record["id"]: record["idf"]
                for record in tx.run(
                    "MATCH (s:Symptom) WHERE s.id IN $ids RETURN s.id AS id, s.idf AS idf",
                    ids=symptom_ids,
                )
            }
            assert second == first
        finally:
            tx.rollback()
