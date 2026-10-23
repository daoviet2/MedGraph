"""Kiểm thử tích hợp áp dụng schema lên Neo4j (F-007).

Yêu cầu acceptance:
- Chạy apply 2 lần không lỗi (tính idempotent).
- SHOW CONSTRAINTS chứa đủ constraint cho mọi NodeLabel.
- SHOW INDEXES chứa symptom_alias và disease_alias.
"""

import pytest
from neo4j import Driver

from medgraph.graph.schema import NodeLabel, apply_schema

pytestmark = pytest.mark.integration


def test_apply_schema_idempotency(driver: Driver) -> None:
    """Chạy apply_schema hai lần liên tiếp không gây lỗi và cho kết quả nhất quán."""
    res1 = apply_schema(driver)
    res2 = apply_schema(driver)

    assert res1["statements_executed"] > 0
    assert res1["statements_executed"] == res2["statements_executed"]
    assert res1["constraints_count"] == res2["constraints_count"]
    assert res1["indexes_count"] == res2["indexes_count"]


def test_constraints_present_for_all_node_labels(driver: Driver) -> None:
    """SHOW CONSTRAINTS chứa đủ unique constraint trên id cho mọi NodeLabel."""
    apply_schema(driver)

    with driver.session() as session:
        result = session.run("SHOW CONSTRAINTS")
        records = [record.data() for record in result]

    # Kiểm tra từng nhãn NodeLabel
    for label in NodeLabel:
        matching = []
        for rec in records:
            labels = rec.get("labelsOrTypes") or []
            props = rec.get("properties") or []
            constraint_type = rec.get("type", "")
            if label.value in labels and "id" in props and "UNIQUE" in constraint_type.upper():
                matching.append(rec)

        assert len(matching) == 1, (
            f"NodeLabel '{label.value}' phải có đúng 1 unique constraint trên id, "
            f"tìm thấy: {len(matching)} trong {records}"
        )


def test_fulltext_indexes_present(driver: Driver) -> None:
    """SHOW INDEXES chứa symptom_alias và disease_alias."""
    apply_schema(driver)

    with driver.session() as session:
        result = session.run("SHOW INDEXES")
        records = [record.data() for record in result]

    index_names = {rec.get("name") for rec in records}
    assert "symptom_alias" in index_names, (
        f"Không tìm thấy index 'symptom_alias' trong {index_names}"
    )
    assert "disease_alias" in index_names, (
        f"Không tìm thấy index 'disease_alias' trong {index_names}"
    )
