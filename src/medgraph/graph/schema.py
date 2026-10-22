"""Hợp đồng đồ thị tri thức (Knowledge Graph Schema) cho MedGraph.

Đóng băng theo quy tắc R7 (AGENTS.md). Định nghĩa hằng số nhãn Node, loại Relationship,
phiên bản schema và ánh xạ từ EdgeRecord sang RelType.
"""

from enum import StrEnum
from pathlib import Path

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

GRAPH_SCHEMA_VERSION: str = "1.0.0"

SCHEMA_CYPHER_PATH: Path = Path(__file__).parent / "schema.cypher"


class NodeLabel(StrEnum):
    """Tập hợp nhãn (Labels) cho các node trong Knowledge Graph."""

    SYMPTOM = "Symptom"
    DISEASE = "Disease"
    RISK_FACTOR = "RiskFactor"
    LAB_TEST = "LabTest"
    SOURCE_DOC = "SourceDoc"


class RelType(StrEnum):
    """Tập hợp loại quan hệ (Relationship Types) trong Knowledge Graph."""

    INDICATES = "INDICATES"
    HAS_RISK_FACTOR = "HAS_RISK_FACTOR"
    CONFIRMED_BY = "CONFIRMED_BY"
    DIFFERENTIAL_OF = "DIFFERENTIAL_OF"
    DOCUMENTED_IN = "DOCUMENTED_IN"
    IS_A = "IS_A"
    SUPERSEDED_BY = "SUPERSEDED_BY"


EDGE_RECORD_TO_REL_TYPE: dict[type[EdgeRecord], RelType] = {
    IndicatesEdge: RelType.INDICATES,
    HasRiskFactorEdge: RelType.HAS_RISK_FACTOR,
    ConfirmedByEdge: RelType.CONFIRMED_BY,
    DifferentialOfEdge: RelType.DIFFERENTIAL_OF,
    DocumentedInEdge: RelType.DOCUMENTED_IN,
    IsAEdge: RelType.IS_A,
    SupersededByEdge: RelType.SUPERSEDED_BY,
}


def load_schema_cypher_statements(file_path: Path | None = None) -> list[str]:
    """Đọc file schema.cypher và tách thành danh sách các câu lệnh Cypher độc lập.

    Bỏ qua các dòng chú thích (//) và dòng trống.
    """
    path = file_path or SCHEMA_CYPHER_PATH
    content = path.read_text(encoding="utf-8")

    # Loại bỏ dòng chú thích và gom nhóm câu lệnh theo dấu chấm phẩy
    cleaned_lines = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        cleaned_lines.append(line)

    raw_text = "\n".join(cleaned_lines)
    statements = [stmt.strip() for stmt in raw_text.split(";") if stmt.strip()]
    return statements
