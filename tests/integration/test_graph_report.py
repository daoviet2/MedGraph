"""Kiểm tra báo cáo graph trên seed_mini trong transaction rollback."""

from pathlib import Path

import pytest
from neo4j import Driver

from medgraph.graph.report import build_graph_health_report
from medgraph.graph.repository import Neo4jGraphRepository
from medgraph.graph.seed_reader import read_seed

SEED_MINI_VALID = Path(__file__).resolve().parents[1] / "fixtures" / "seed_mini" / "valid"


@pytest.mark.integration
def test_graph_report_matches_seed_mini_and_detects_missing_source(driver: Driver) -> None:
    bundle = read_seed(SEED_MINI_VALID)
    repo = Neo4jGraphRepository(driver, batch_size=50)

    with driver.session() as session:
        tx = session.begin_transaction()
        try:
            # Cô lập fixture khỏi graph đang có; rollback toàn bộ khi test kết thúc.
            tx.run("MATCH (n) DETACH DELETE n").consume()
            repo.upsert_source_docs(bundle.sources, tx=tx)
            repo.upsert_diseases(bundle.diseases, tx=tx)
            repo.upsert_symptoms(bundle.symptoms, tx=tx)
            repo.upsert_risk_factors(bundle.risk_factors, tx=tx)
            repo.upsert_lab_tests(bundle.lab_tests, tx=tx)
            repo.upsert_indicates_edges(bundle.indicates, tx=tx)
            repo.upsert_has_risk_factor_edges(bundle.has_risk_factors, tx=tx)
            repo.upsert_confirmed_by_edges(bundle.confirmed_by, tx=tx)
            repo.upsert_differential_of_edges(bundle.differential_of, tx=tx)
            repo.upsert_documented_in_edges(bundle.documented_in, tx=tx)
            repo.upsert_is_a_edges(bundle.is_a, tx=tx)
            repo.upsert_superseded_by_edges(bundle.superseded_by, tx=tx)

            report = build_graph_health_report(repo, tx=tx)
            nodes = {item.name: item.count for item in report.node_counts}
            edges = {item.name: item.count for item in report.edge_counts}
            provenance = {item.name: item for item in report.provenance_mix}

            assert nodes == {
                "Disease": 2,
                "LabTest": 2,
                "RiskFactor": 1,
                "SourceDoc": 3,
                "Symptom": 3,
            }
            assert edges == {
                "CONFIRMED_BY": 1,
                "DIFFERENTIAL_OF": 1,
                "DOCUMENTED_IN": 1,
                "HAS_RISK_FACTOR": 1,
                "INDICATES": 3,
                "IS_A": 1,
                "SUPERSEDED_BY": 1,
            }
            assert report.total_edges == report.edges_with_source == 9
            assert report.source_coverage_percent == 100.0
            assert provenance["curated"].count == 9
            assert provenance["curated"].percent == 100.0
            assert report.active_source_docs == 2
            assert report.total_source_docs == 3
            assert report.active_source_percent == pytest.approx(200 / 3)
            assert report.orphan_diseases == 0
            assert report.has_complete_provenance

            # Một cạnh không có source_id phải làm cổng kiểm tra báo lỗi.
            tx.run(
                "MATCH (:Symptom {id: $symptom_id})-[r:INDICATES]->"
                "(:Disease {id: $disease_id}) REMOVE r.source_id",
                symptom_id=bundle.indicates[0].symptom_id,
                disease_id=bundle.indicates[0].disease_id,
            ).consume()
            incomplete = build_graph_health_report(repo, tx=tx)
            assert incomplete.edges_with_source == 8
            assert incomplete.source_coverage_percent == pytest.approx(800 / 9)
            assert not incomplete.has_complete_provenance
        finally:
            tx.rollback()
