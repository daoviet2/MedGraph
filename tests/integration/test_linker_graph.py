"""Xác nhận chiều IS_A và danh mục Neo4j trong transaction rollback."""

import pytest
from neo4j import Driver

from medgraph.graph.repository import Neo4jGraphRepository
from medgraph.models.schemas import EntityType


@pytest.mark.integration
def test_catalog_and_parent_direction(driver: Driver) -> None:
    repository = Neo4jGraphRepository(driver)
    with driver.session() as session:
        tx = session.begin_transaction()
        try:
            tx.run(
                "CREATE (c:Symptom {id:'test:child', name_vi:'Ho khan', review_status:'approved'})"
                "-[:IS_A]->(p:Symptom {id:'test:parent', name_vi:'Ho', review_status:'approved'})"
            )
            assert ("test:parent", 1) in repository.parents("test:child", tx=tx)
            assert ("test:child", 1) not in repository.parents("test:parent", tx=tx)
            assert any(
                item.id == "test:child" for item in repository.entries(EntityType.SYMPTOM, tx=tx)
            )
        finally:
            tx.rollback()
