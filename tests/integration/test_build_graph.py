"""Integration test cho việc nạp đồ thị idempotent vào Neo4j thật (F-013).

Yêu cầu nghiệm thu F-013:
- Nạp seed_mini 2 lần -> số node và số cạnh theo từng label/type giống hệt nhau.
- Tự động skip khi Neo4j không khả dụng (thông qua conftest.py).
"""

from pathlib import Path

import pytest
from neo4j import Driver

from medgraph.graph.loader import GraphLoader
from medgraph.graph.repository import Neo4jGraphRepository
from medgraph.graph.schema import apply_schema
from medgraph.graph.seed_reader import read_seed

SEED_MINI_VALID = Path(__file__).resolve().parents[1] / "fixtures" / "seed_mini" / "valid"


@pytest.mark.integration
def test_idempotent_graph_loading_on_neo4j(driver: Driver):
    """Khẳng định nạp seed_mini 2 lần vào Neo4j cho cùng số lượng node và cạnh."""
    # 1. Áp dụng schema
    apply_schema(driver)

    # 2. Xóa các node của fixture mini trước khi test để đảm bảo môi trường sạch
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")

    bundle = read_seed(SEED_MINI_VALID)
    repo = Neo4jGraphRepository(driver, batch_size=50)
    loader = GraphLoader(repo)

    # 3. Nạp lần 1
    report1 = loader.load(bundle)
    assert report1.is_success is True, f"Nạp lần 1 thất bại: {report1.failed_sources}"
    counts1 = repo.get_counts()

    # Khẳng định các node và edge đã được tạo trong Neo4j
    assert counts1["SourceDoc"] == 3
    assert counts1["Disease"] == 2
    assert counts1["Symptom"] == 3
    assert counts1["INDICATES"] == 3

    # 4. Nạp lần 2 trên cùng database
    report2 = loader.load(bundle)
    assert report2.is_success is True, f"Nạp lần 2 thất bại: {report2.failed_sources}"
    counts2 = repo.get_counts()

    # 5. Khẳng định số lượng node và cạnh của từng label/rel_type không đổi
    assert counts1 == counts2, f"Số lượng không đồng nhất sau 2 lần nạp: {counts1} != {counts2}"
