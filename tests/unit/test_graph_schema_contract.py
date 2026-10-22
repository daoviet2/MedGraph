"""Unit tests kiểm chứng hợp đồng đồ thị Knowledge Graph (F-005).

Kiểm tra:
- Khai báo StrEnum NodeLabel, RelType và GRAPH_SCHEMA_VERSION trong schema.py.
- Ánh xạ 1-1 giữa các lớp EdgeRecord trong graph_records.py và RelType.
- Cú pháp và nội dung của schema.cypher (không cần kết nối Neo4j):
  + Mỗi NodeLabel có đúng một unique constraint trên id.
  + Đầy đủ fulltext indexes symptom_alias và disease_alias.
  + 100% câu lệnh Cypher sử dụng IF NOT EXISTS (idempotency).
"""

import re

import pytest

from medgraph.graph.schema import (
    EDGE_RECORD_TO_REL_TYPE,
    GRAPH_SCHEMA_VERSION,
    SCHEMA_CYPHER_PATH,
    NodeLabel,
    RelType,
    load_schema_cypher_statements,
)
from medgraph.models.graph_records import (
    ConfirmedByEdge,
    DifferentialOfEdge,
    DocumentedInEdge,
    EdgeRecord,
    HasRiskFactorEdge,
    IndicatesEdge,
    IsAEdge,
    SupersededByEdge,
)

pytestmark = pytest.mark.unit


def test_schema_version_defined() -> None:
    """GRAPH_SCHEMA_VERSION được định nghĩa và tuân theo SemVer."""
    assert isinstance(GRAPH_SCHEMA_VERSION, str)
    assert re.match(r"^\d+\.\d+\.\d+$", GRAPH_SCHEMA_VERSION)


def test_node_label_enum_members() -> None:
    """NodeLabel khai báo đủ 5 label thực thể chính theo schema."""
    expected_labels = {"Symptom", "Disease", "RiskFactor", "LabTest", "SourceDoc"}
    actual_labels = {label.value for label in NodeLabel}
    assert actual_labels == expected_labels


def test_rel_type_enum_members() -> None:
    """RelType khai báo đủ 7 loại quan hệ theo docs/04 §2."""
    expected_rels = {
        "INDICATES",
        "HAS_RISK_FACTOR",
        "CONFIRMED_BY",
        "DIFFERENTIAL_OF",
        "DOCUMENTED_IN",
        "IS_A",
        "SUPERSEDED_BY",
    }
    actual_rels = {rel.value for rel in RelType}
    assert actual_rels == expected_rels


def test_edge_record_to_rel_type_mapping() -> None:
    """Mỗi lớp *Edge trong graph_records.py ánh xạ tới đúng một RelType tương ứng."""
    expected_edges: set[type[EdgeRecord]] = {
        IndicatesEdge,
        HasRiskFactorEdge,
        ConfirmedByEdge,
        DifferentialOfEdge,
        DocumentedInEdge,
        IsAEdge,
        SupersededByEdge,
    }

    # Tập hợp các lớp được mapping
    mapped_edges = set(EDGE_RECORD_TO_REL_TYPE.keys())
    assert mapped_edges == expected_edges

    # Đảm bảo mỗi RelType đều có lớp tương ứng
    mapped_rel_types = set(EDGE_RECORD_TO_REL_TYPE.values())
    assert mapped_rel_types == set(RelType)

    # Kiểm tra từng ánh xạ cụ thể
    assert EDGE_RECORD_TO_REL_TYPE[IndicatesEdge] == RelType.INDICATES
    assert EDGE_RECORD_TO_REL_TYPE[HasRiskFactorEdge] == RelType.HAS_RISK_FACTOR
    assert EDGE_RECORD_TO_REL_TYPE[ConfirmedByEdge] == RelType.CONFIRMED_BY
    assert EDGE_RECORD_TO_REL_TYPE[DifferentialOfEdge] == RelType.DIFFERENTIAL_OF
    assert EDGE_RECORD_TO_REL_TYPE[DocumentedInEdge] == RelType.DOCUMENTED_IN
    assert EDGE_RECORD_TO_REL_TYPE[IsAEdge] == RelType.IS_A
    assert EDGE_RECORD_TO_REL_TYPE[SupersededByEdge] == RelType.SUPERSEDED_BY


def test_schema_cypher_file_exists() -> None:
    """File schema.cypher tồn tại và có nội dung."""
    assert SCHEMA_CYPHER_PATH.exists()
    assert SCHEMA_CYPHER_PATH.is_file()
    assert len(SCHEMA_CYPHER_PATH.read_text(encoding="utf-8").strip()) > 0


def test_all_statements_use_if_not_exists() -> None:
    """100% câu lệnh Cypher trong schema.cypher phải có IF NOT EXISTS."""
    statements = load_schema_cypher_statements()
    assert len(statements) >= 7  # Ít nhất 5 constraints + 2 fulltext indexes

    for stmt in statements:
        # Chuẩn hóa khoảng trắng để kiểm tra
        normalized = " ".join(stmt.split()).upper()
        assert "IF NOT EXISTS" in normalized, f"Câu lệnh Cypher thiếu 'IF NOT EXISTS':\n{stmt}"


def test_every_node_label_has_unique_constraint_on_id() -> None:
    """Mỗi NodeLabel có đúng một unique constraint trên trường id."""
    statements = load_schema_cypher_statements()

    for label in NodeLabel:
        matching = []
        for stmt in statements:
            clean = " ".join(stmt.split())
            # Match dạng: CREATE CONSTRAINT ... FOR (x:Label) REQUIRE x.id IS UNIQUE
            pattern = rf"FOR\s*\(\w+:{label.value}\)\s*REQUIRE\s*\w+\.id\s*IS\s*UNIQUE"
            if re.search(pattern, clean, re.IGNORECASE):
                matching.append(stmt)

        assert len(matching) == 1, (
            f"NodeLabel '{label.value}' phải có đúng 1 unique constraint trên id, tìm thấy: "
            f"{len(matching)}"
        )


def test_fulltext_indexes_for_aliases() -> None:
    """schema.cypher định nghĩa fulltext indexes cho symptom_alias và disease_alias."""
    statements = load_schema_cypher_statements()
    all_cypher = "\n".join(" ".join(stmt.split()) for stmt in statements)

    # symptom_alias
    symptom_pattern = (
        r"CREATE\s+FULLTEXT\s+INDEX\s+symptom_alias\s+IF\s+NOT\s+EXISTS\s+"
        r"FOR\s*\(\w+:Symptom\)\s+ON\s+EACH\s*\[\w+\.name_vi,\s*\w+\.aliases_vi,\s*\w+\.aliases_norm\]"
    )
    assert re.search(symptom_pattern, all_cypher, re.IGNORECASE), (
        "Không tìm thấy fulltext index symptom_alias trên [name_vi, aliases_vi, aliases_norm]"
    )

    # disease_alias
    disease_pattern = (
        r"CREATE\s+FULLTEXT\s+INDEX\s+disease_alias\s+IF\s+NOT\s+EXISTS\s+"
        r"FOR\s*\(\w+:Disease\)\s+ON\s+EACH\s*\[\w+\.name_vi,\s*\w+\.aliases_vi,\s*\w+\.aliases_norm\]"
    )
    assert re.search(disease_pattern, all_cypher, re.IGNORECASE), (
        "Không tìm thấy fulltext index disease_alias trên [name_vi, aliases_vi, aliases_norm]"
    )
