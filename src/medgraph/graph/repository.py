"""Graph Write Repository cho MedGraph .

Tuân thủ kiến trúc và quy tắc:
- Tách biệt logic nạp khỏi Cypher thông qua Protocol GraphWriteRepository.
- Repository là nơi DUY NHẤT chứa Cypher ghi; mọi câu lệnh dùng tham số $batch.
- Mọi thao tác dùng MERGE theo id (node) và theo (start, type, end) (cạnh).
- Idempotent: chạy nhiều lần ra cùng một kết quả mà không làm biến đổi số lượng node/cạnh.
- Cung cấp FakeGraphRepository phục vụ unit test in-memory không cần Neo4j.
"""

import copy
import logging
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from datetime import date
from typing import Any, Protocol, TypeVar

from neo4j import Driver, Transaction

from medgraph.graph.schema import NodeLabel, RelType
from medgraph.models.aliases import normalize_alias
from medgraph.models.graph_records import (
    ConfirmedByEdge,
    DifferentialOfEdge,
    DiseaseRecord,
    DocumentedInEdge,
    HasRiskFactorEdge,
    IndicatesEdge,
    IsAEdge,
    LabTestRecord,
    RiskFactorRecord,
    SourceDocRecord,
    SupersededByEdge,
    SymptomRecord,
)
from medgraph.models.report import GraphHealthSnapshot, NamedCount

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _chunk_list(items: Sequence[T], chunk_size: int) -> Generator[list[T], None, None]:
    """Chia nhỏ danh sách thành các lô có kích thước chunk_size."""
    for i in range(0, len(items), chunk_size):
        yield list(items[i : i + chunk_size])


def _serialize_date(val: date | str | None) -> str | None:
    """Chuyển đổi date thành chuỗi ISO."""
    if val is None:
        return None
    if isinstance(val, date):
        return val.isoformat()
    return str(val).strip()


class GraphWriteRepository(Protocol):
    """Protocol giao tiếp ghi dữ liệu vào Knowledge Graph."""

    @contextmanager
    def transaction(self) -> Generator[Any, None, None]:
        """Tạo transaction context manager cho một Unit of Work."""
        ...

    def upsert_source_docs(self, docs: list[SourceDocRecord], tx: Any = None) -> int: ...

    def upsert_diseases(self, diseases: list[DiseaseRecord], tx: Any = None) -> int: ...

    def upsert_symptoms(self, symptoms: list[SymptomRecord], tx: Any = None) -> int: ...

    def upsert_risk_factors(self, risk_factors: list[RiskFactorRecord], tx: Any = None) -> int: ...

    def upsert_lab_tests(self, lab_tests: list[LabTestRecord], tx: Any = None) -> int: ...

    def upsert_indicates_edges(self, edges: list[IndicatesEdge], tx: Any = None) -> int: ...

    def upsert_has_risk_factor_edges(
        self, edges: list[HasRiskFactorEdge], tx: Any = None
    ) -> int: ...

    def upsert_confirmed_by_edges(self, edges: list[ConfirmedByEdge], tx: Any = None) -> int: ...

    def upsert_differential_of_edges(
        self, edges: list[DifferentialOfEdge], tx: Any = None
    ) -> int: ...

    def upsert_documented_in_edges(self, edges: list[DocumentedInEdge], tx: Any = None) -> int: ...

    def upsert_is_a_edges(self, edges: list[IsAEdge], tx: Any = None) -> int: ...

    def upsert_superseded_by_edges(self, edges: list[SupersededByEdge], tx: Any = None) -> int: ...

    def get_counts(self) -> dict[str, int]:
        """Đếm số node theo label và số cạnh theo rel type."""
        ...


class Neo4jGraphRepository:
    """Hiện thực GraphWriteRepository trên cơ sở dữ liệu Neo4j sử dụng Cypher MERGE."""

    def __init__(self, driver: Driver, batch_size: int = 500) -> None:
        self.driver = driver
        self.batch_size = max(1, batch_size)

    @contextmanager
    def transaction(self) -> Generator[Transaction, None, None]:
        """Mở Neo4j session và transaction cho một Unit of Work."""
        with self.driver.session() as session:
            tx = session.begin_transaction()
            try:
                yield tx
                tx.commit()
            except Exception:
                tx.rollback()
                raise

    def _execute(self, query: str, batch: list[dict[str, Any]], tx: Transaction | None) -> None:
        if tx is not None:
            tx.run(query, batch=batch)
        else:
            with self.transaction() as new_tx:
                new_tx.run(query, batch=batch)

    def search_symptom_alias(self, phrase: str, tx: Transaction | None = None) -> list[str]:
        """Tra fulltext symptom bằng dạng không dấu để kiểm tra alias đã nạp."""
        query = """
        CALL db.index.fulltext.queryNodes($index_name, $phrase)
        YIELD node, score
        WHERE node:Symptom
        WITH node, score, $normalized IN coalesce(node.aliases_norm, []) AS exact_alias
        RETURN node.id AS id
        ORDER BY exact_alias DESC, score DESC
        """
        normalized = normalize_alias(phrase)
        escaped = normalized.replace("\\", "\\\\").replace('"', '\\"')
        params = {
            "index_name": "symptom_alias",
            "phrase": f'"{escaped}"',
            "normalized": normalized,
        }
        if tx is not None:
            return [record["id"] for record in tx.run(query, **params)]
        with self.driver.session() as session:
            return [record["id"] for record in session.run(query, **params)]

    # -------------------------------------------------------------------------
    # Node Upserts (MERGE theo id, SET cập nhật thuộc tính)
    # -------------------------------------------------------------------------

    def upsert_source_docs(self, docs: list[SourceDocRecord], tx: Transaction | None = None) -> int:
        if not docs:
            return 0
        query = """
        UNWIND $batch AS row
        MERGE (n:SourceDoc {id: row.id})
        SET n.title = row.title,
            n.publisher = row.publisher,
            n.year = row.year,
            n.url = row.url,
            n.license = row.license,
            n.effective_from = row.effective_from,
            n.effective_to = row.effective_to,
            n.status = row.status,
            n.superseded_by = row.superseded_by,
            n.review_status = row.review_status
        """
        for chunk in _chunk_list(docs, self.batch_size):
            payload = [
                {
                    "id": d.id,
                    "title": d.title,
                    "publisher": d.publisher,
                    "year": d.year,
                    "url": d.url,
                    "license": d.license,
                    "effective_from": _serialize_date(d.effective_from),
                    "effective_to": _serialize_date(d.effective_to),
                    "status": d.status,
                    "superseded_by": d.superseded_by,
                    "review_status": d.review_status.value,
                }
                for d in chunk
            ]
            self._execute(query, payload, tx)
        return len(docs)

    def upsert_diseases(self, diseases: list[DiseaseRecord], tx: Transaction | None = None) -> int:
        if not diseases:
            return 0
        query = """
        UNWIND $batch AS row
        MERGE (n:Disease {id: row.id})
        SET n.name_en = row.name_en,
            n.name_vi = row.name_vi,
            n.aliases_vi = row.aliases_vi,
            n.aliases_norm = row.aliases_norm,
            n.category = row.category,
            n.urgency_default = row.urgency_default,
            n.danger_level = row.danger_level,
            n.cant_miss = row.cant_miss,
            n.review_status = row.review_status
        """
        for chunk in _chunk_list(diseases, self.batch_size):
            payload = [
                {
                    "id": d.id,
                    "name_en": d.name_en,
                    "name_vi": d.name_vi,
                    "aliases_vi": d.aliases_vi,
                    "aliases_norm": [normalize_alias(a) for a in d.aliases_vi],
                    "category": d.category,
                    "urgency_default": d.urgency_default.value,
                    "danger_level": d.danger_level,
                    "cant_miss": d.cant_miss,
                    "review_status": d.review_status.value,
                }
                for d in chunk
            ]
            self._execute(query, payload, tx)
        return len(diseases)

    def upsert_symptoms(self, symptoms: list[SymptomRecord], tx: Transaction | None = None) -> int:
        if not symptoms:
            return 0
        query = """
        UNWIND $batch AS row
        MERGE (n:Symptom {id: row.id})
        SET n.name_en = row.name_en,
            n.name_vi = row.name_vi,
            n.aliases_vi = row.aliases_vi,
            n.aliases_norm = row.aliases_norm,
            n.is_red_flag = row.is_red_flag,
            n.review_status = row.review_status
        """
        for chunk in _chunk_list(symptoms, self.batch_size):
            payload = [
                {
                    "id": s.id,
                    "name_en": s.name_en,
                    "name_vi": s.name_vi,
                    "aliases_vi": s.aliases_vi,
                    "aliases_norm": [normalize_alias(a) for a in s.aliases_vi],
                    "is_red_flag": s.is_red_flag,
                    "review_status": s.review_status.value,
                }
                for s in chunk
            ]
            self._execute(query, payload, tx)
        return len(symptoms)

    def upsert_risk_factors(
        self, risk_factors: list[RiskFactorRecord], tx: Transaction | None = None
    ) -> int:
        if not risk_factors:
            return 0
        query = """
        UNWIND $batch AS row
        MERGE (n:RiskFactor {id: row.id})
        SET n.name_vi = row.name_vi,
            n.type = row.type,
            n.review_status = row.review_status
        """
        for chunk in _chunk_list(risk_factors, self.batch_size):
            payload = [
                {
                    "id": r.id,
                    "name_vi": r.name_vi,
                    "type": r.type,
                    "review_status": r.review_status.value,
                }
                for r in chunk
            ]
            self._execute(query, payload, tx)
        return len(risk_factors)

    def upsert_lab_tests(
        self, lab_tests: list[LabTestRecord], tx: Transaction | None = None
    ) -> int:
        if not lab_tests:
            return 0
        query = """
        UNWIND $batch AS row
        MERGE (n:LabTest {id: row.id})
        SET n.name_vi = row.name_vi,
            n.purpose = row.purpose,
            n.review_status = row.review_status
        """
        for chunk in _chunk_list(lab_tests, self.batch_size):
            payload = [
                {
                    "id": lt.id,
                    "name_vi": lt.name_vi,
                    "purpose": lt.purpose,
                    "review_status": lt.review_status.value,
                }
                for lt in chunk
            ]
            self._execute(query, payload, tx)
        return len(lab_tests)

    # -------------------------------------------------------------------------
    # Edge Upserts (MERGE theo start, type, end)
    # -------------------------------------------------------------------------

    def upsert_indicates_edges(
        self, edges: list[IndicatesEdge], tx: Transaction | None = None
    ) -> int:
        if not edges:
            return 0
        query = """
        UNWIND $batch AS row
        MATCH (s:Symptom {id: row.symptom_id})
        MATCH (d:Disease {id: row.disease_id})
        MERGE (s)-[r:INDICATES]->(d)
        SET r.weight = row.weight,
            r.is_cardinal = row.is_cardinal,
            r.source_id = row.source_id,
            r.provenance = row.provenance,
            r.evidence_count = row.evidence_count,
            r.confidence = row.confidence
        """
        for chunk in _chunk_list(edges, self.batch_size):
            payload = [
                {
                    "symptom_id": e.symptom_id,
                    "disease_id": e.disease_id,
                    "weight": e.weight,
                    "is_cardinal": e.is_cardinal,
                    "source_id": e.source_id,
                    "provenance": e.provenance.value,
                    "evidence_count": e.evidence_count,
                    "confidence": e.confidence,
                }
                for e in chunk
            ]
            self._execute(query, payload, tx)
        return len(edges)

    def upsert_has_risk_factor_edges(
        self, edges: list[HasRiskFactorEdge], tx: Transaction | None = None
    ) -> int:
        if not edges:
            return 0
        query = """
        UNWIND $batch AS row
        MATCH (d:Disease {id: row.disease_id})
        MATCH (r:RiskFactor {id: row.risk_id})
        MERGE (d)-[rel:HAS_RISK_FACTOR]->(r)
        SET rel.weight = row.weight,
            rel.source_id = row.source_id,
            rel.provenance = row.provenance,
            rel.evidence_count = row.evidence_count,
            rel.confidence = row.confidence
        """
        for chunk in _chunk_list(edges, self.batch_size):
            payload = [
                {
                    "disease_id": e.disease_id,
                    "risk_id": e.risk_id,
                    "weight": e.weight,
                    "source_id": e.source_id,
                    "provenance": e.provenance.value,
                    "evidence_count": e.evidence_count,
                    "confidence": e.confidence,
                }
                for e in chunk
            ]
            self._execute(query, payload, tx)
        return len(edges)

    def upsert_confirmed_by_edges(
        self, edges: list[ConfirmedByEdge], tx: Transaction | None = None
    ) -> int:
        if not edges:
            return 0
        query = """
        UNWIND $batch AS row
        MATCH (d:Disease {id: row.disease_id})
        MATCH (l:LabTest {id: row.lab_id})
        MERGE (d)-[rel:CONFIRMED_BY]->(l)
        SET rel.role = row.role,
            rel.source_id = row.source_id,
            rel.provenance = row.provenance,
            rel.evidence_count = row.evidence_count,
            rel.confidence = row.confidence
        """
        for chunk in _chunk_list(edges, self.batch_size):
            payload = [
                {
                    "disease_id": e.disease_id,
                    "lab_id": e.lab_id,
                    "role": e.role.value,
                    "source_id": e.source_id,
                    "provenance": e.provenance.value,
                    "evidence_count": e.evidence_count,
                    "confidence": e.confidence,
                }
                for e in chunk
            ]
            self._execute(query, payload, tx)
        return len(edges)

    def upsert_differential_of_edges(
        self, edges: list[DifferentialOfEdge], tx: Transaction | None = None
    ) -> int:
        if not edges:
            return 0
        query = """
        UNWIND $batch AS row
        MATCH (d:Disease {id: row.disease_id})
        MATCH (other:Disease {id: row.other_id})
        MERGE (d)-[rel:DIFFERENTIAL_OF]->(other)
        SET rel.distinguishing_features = row.distinguishing_features,
            rel.source_id = row.source_id,
            rel.provenance = row.provenance,
            rel.evidence_count = row.evidence_count,
            rel.confidence = row.confidence
        """
        for chunk in _chunk_list(edges, self.batch_size):
            payload = [
                {
                    "disease_id": e.disease_id,
                    "other_id": e.other_id,
                    "distinguishing_features": e.distinguishing_features,
                    "source_id": e.source_id,
                    "provenance": e.provenance.value,
                    "evidence_count": e.evidence_count,
                    "confidence": e.confidence,
                }
                for e in chunk
            ]
            self._execute(query, payload, tx)
        return len(edges)

    def upsert_documented_in_edges(
        self, edges: list[DocumentedInEdge], tx: Transaction | None = None
    ) -> int:
        if not edges:
            return 0
        query = """
        UNWIND $batch AS row
        MATCH (d:Disease {id: row.disease_id})
        MATCH (s:SourceDoc {id: row.source_doc_id})
        MERGE (d)-[rel:DOCUMENTED_IN]->(s)
        SET rel.section = row.section,
            rel.source_id = row.source_id,
            rel.provenance = row.provenance,
            rel.evidence_count = row.evidence_count,
            rel.confidence = row.confidence
        """
        for chunk in _chunk_list(edges, self.batch_size):
            payload = [
                {
                    "disease_id": e.disease_id,
                    "source_doc_id": e.source_doc_id,
                    "section": e.section,
                    "source_id": e.source_id,
                    "provenance": e.provenance.value,
                    "evidence_count": e.evidence_count,
                    "confidence": e.confidence,
                }
                for e in chunk
            ]
            self._execute(query, payload, tx)
        return len(edges)

    def upsert_is_a_edges(self, edges: list[IsAEdge], tx: Transaction | None = None) -> int:
        if not edges:
            return 0
        query = """
        UNWIND $batch AS row
        MATCH (c:Symptom {id: row.child_id})
        MATCH (p:Symptom {id: row.parent_id})
        MERGE (c)-[rel:IS_A]->(p)
        SET rel.source_id = row.source_id,
            rel.provenance = row.provenance,
            rel.evidence_count = row.evidence_count,
            rel.confidence = row.confidence
        """
        for chunk in _chunk_list(edges, self.batch_size):
            payload = [
                {
                    "child_id": e.child_id,
                    "parent_id": e.parent_id,
                    "source_id": e.source_id,
                    "provenance": e.provenance.value,
                    "evidence_count": e.evidence_count,
                    "confidence": e.confidence,
                }
                for e in chunk
            ]
            self._execute(query, payload, tx)
        return len(edges)

    def upsert_superseded_by_edges(
        self, edges: list[SupersededByEdge], tx: Transaction | None = None
    ) -> int:
        if not edges:
            return 0
        query = """
        UNWIND $batch AS row
        MATCH (old:SourceDoc {id: row.old_id})
        MATCH (new:SourceDoc {id: row.new_id})
        MERGE (old)-[rel:SUPERSEDED_BY]->(new)
        SET rel.effective_from = row.effective_from,
            rel.source_id = row.source_id,
            rel.provenance = row.provenance,
            rel.evidence_count = row.evidence_count,
            rel.confidence = row.confidence
        """
        for chunk in _chunk_list(edges, self.batch_size):
            payload = [
                {
                    "old_id": e.old_id,
                    "new_id": e.new_id,
                    "effective_from": _serialize_date(e.effective_from),
                    "source_id": e.source_id,
                    "provenance": e.provenance.value,
                    "evidence_count": e.evidence_count,
                    "confidence": e.confidence,
                }
                for e in chunk
            ]
            self._execute(query, payload, tx)
        return len(edges)

    def get_counts(self) -> dict[str, int]:
        """Lấy số lượng node theo label và edge theo relationship type từ Neo4j."""
        counts: dict[str, int] = {}
        with self.driver.session() as session:
            # Đếm nodes
            labels = ["SourceDoc", "Disease", "Symptom", "RiskFactor", "LabTest"]
            for label in labels:
                result = session.run(f"MATCH (n:{label}) RETURN count(n) AS cnt")
                record = result.single()
                counts[label] = record["cnt"] if record else 0

            # Đếm edges
            rel_types = [
                "INDICATES",
                "HAS_RISK_FACTOR",
                "CONFIRMED_BY",
                "DIFFERENTIAL_OF",
                "DOCUMENTED_IN",
                "IS_A",
                "SUPERSEDED_BY",
            ]
            for r_type in rel_types:
                result = session.run(f"MATCH ()-[r:{r_type}]->() RETURN count(r) AS cnt")
                record = result.single()
                counts[r_type] = record["cnt"] if record else 0

        return counts

    def read_graph_health(self, tx: Transaction | None = None) -> GraphHealthSnapshot:
        """Đọc snapshot nhất quán của graph cho báo cáo truy vết nguồn."""
        if tx is None:
            with self.transaction() as read_tx:
                return self._read_graph_health(read_tx)
        return self._read_graph_health(tx)

    @staticmethod
    def _read_graph_health(tx: Transaction) -> GraphHealthSnapshot:
        node_totals = {
            record["name"]: record["count"]
            for record in tx.run(
                "MATCH (n) UNWIND labels(n) AS name RETURN name, count(*) AS count"
            )
        }
        edge_totals = {
            record["name"]: record["count"]
            for record in tx.run("MATCH ()-[r]->() RETURN type(r) AS name, count(r) AS count")
        }
        provenance_totals = {
            record["name"]: record["count"]
            for record in tx.run(
                "MATCH ()-[r]->() RETURN coalesce(r.provenance, 'missing') AS name, "
                "count(r) AS count"
            )
        }
        coverage = tx.run(
            "MATCH ()-[r]->() RETURN count(r) AS total, "
            "count(CASE WHEN r.source_id IS NOT NULL AND trim(r.source_id) <> '' "
            "THEN 1 END) AS sourced"
        ).single()
        sources = tx.run(
            "MATCH (s:SourceDoc) RETURN count(s) AS total, "
            "count(CASE WHEN s.status = 'active' THEN 1 END) AS active"
        ).single()
        orphans = tx.run(
            "MATCH (d:Disease) WHERE NOT EXISTS { "
            "MATCH (:Symptom)-[:INDICATES]->(d) } RETURN count(d) AS count"
        ).single()
        node_names = {label.value for label in NodeLabel} | node_totals.keys()
        edge_names = {rel.value for rel in RelType} | edge_totals.keys()
        return GraphHealthSnapshot(
            node_counts=tuple(
                NamedCount(name=name, count=node_totals.get(name, 0)) for name in sorted(node_names)
            ),
            edge_counts=tuple(
                NamedCount(name=name, count=edge_totals.get(name, 0)) for name in sorted(edge_names)
            ),
            provenance_counts=tuple(
                NamedCount(name=name, count=count)
                for name, count in sorted(provenance_totals.items())
            ),
            total_edges=coverage["total"] if coverage else 0,
            edges_with_source=coverage["sourced"] if coverage else 0,
            total_source_docs=sources["total"] if sources else 0,
            active_source_docs=sources["active"] if sources else 0,
            orphan_diseases=orphans["count"] if orphans else 0,
        )

    def get_disease_count(self, tx: Transaction | None = None) -> int:
        """Đếm mọi Disease hiện có trong graph để làm mẫu số IDF."""
        if tx is not None:
            record = tx.run("MATCH (d:Disease) RETURN count(d) AS total").single()
            return record["total"] if record else 0
        with self.driver.session() as session:
            record = session.run("MATCH (d:Disease) RETURN count(d) AS total").single()
            return record["total"] if record else 0

    def get_symptom_disease_frequencies(self, tx: Transaction | None = None) -> dict[str, int]:
        """Đếm số Disease khác nhau được mỗi Symptom chỉ tới."""
        query = """
        MATCH (s:Symptom)-[:INDICATES]->(d:Disease)
        RETURN s.id AS symptom_id, count(DISTINCT d) AS frequency
        """
        if tx is not None:
            return {record["symptom_id"]: record["frequency"] for record in tx.run(query)}
        with self.driver.session() as session:
            return {record["symptom_id"]: record["frequency"] for record in session.run(query)}

    def update_symptom_idf(
        self, idf_by_symptom: dict[str, float], tx: Transaction | None = None
    ) -> int:
        """Ghi IDF theo lô, dùng id làm khóa để chạy lại an toàn."""
        if not idf_by_symptom:
            return 0
        query = """
        UNWIND $batch AS row
        MATCH (s:Symptom {id: row.id})
        SET s.idf = row.idf
        """
        rows = [{"id": symptom_id, "idf": idf} for symptom_id, idf in idf_by_symptom.items()]
        if tx is not None:
            for chunk in _chunk_list(rows, self.batch_size):
                self._execute(query, chunk, tx)
        else:
            with self.transaction() as new_tx:
                for chunk in _chunk_list(rows, self.batch_size):
                    self._execute(query, chunk, new_tx)
        return len(rows)


class FakeGraphRepository:
    """Hiện thực in-memory của GraphWriteRepository phục vụ unit test độc lập với Neo4j."""

    def __init__(self) -> None:
        # nodes: label -> id -> props
        self.nodes: dict[str, dict[str, dict[str, Any]]] = {
            "SourceDoc": {},
            "Disease": {},
            "Symptom": {},
            "RiskFactor": {},
            "LabTest": {},
        }
        # edges: rel_type -> (start_id, rel_type, end_id) -> props
        self.edges: dict[str, dict[tuple[str, str, str], dict[str, Any]]] = {
            "INDICATES": {},
            "HAS_RISK_FACTOR": {},
            "CONFIRMED_BY": {},
            "DIFFERENTIAL_OF": {},
            "DOCUMENTED_IN": {},
            "IS_A": {},
            "SUPERSEDED_BY": {},
        }
        # Cờ mô phỏng lỗi cho unit testing
        self.fail_on_source_ids: set[str] = set()

    @contextmanager
    def transaction(self) -> Generator["FakeGraphRepository", None, None]:
        """Mô phỏng transaction với khả năng rollback khi có exception."""
        # Tạo snapshot in-memory
        nodes_snapshot = copy.deepcopy(self.nodes)
        edges_snapshot = copy.deepcopy(self.edges)
        try:
            yield self
        except Exception:
            # Rollback về snapshot
            self.nodes = nodes_snapshot
            self.edges = edges_snapshot
            raise

    def upsert_source_docs(self, docs: list[SourceDocRecord], tx: Any = None) -> int:
        for d in docs:
            if d.id in self.fail_on_source_ids:
                raise RuntimeError(f"Simulated error on source: {d.id}")
            self.nodes["SourceDoc"][d.id] = {
                "id": d.id,
                "title": d.title,
                "review_status": d.review_status.value,
            }
        return len(docs)

    def upsert_diseases(self, diseases: list[DiseaseRecord], tx: Any = None) -> int:
        for d in diseases:
            self.nodes["Disease"][d.id] = {
                "id": d.id,
                "name_vi": d.name_vi,
                "review_status": d.review_status.value,
            }
        return len(diseases)

    def upsert_symptoms(self, symptoms: list[SymptomRecord], tx: Any = None) -> int:
        for s in symptoms:
            self.nodes["Symptom"][s.id] = {
                "id": s.id,
                "name_vi": s.name_vi,
                "review_status": s.review_status.value,
            }
        return len(symptoms)

    def upsert_risk_factors(self, risk_factors: list[RiskFactorRecord], tx: Any = None) -> int:
        for r in risk_factors:
            self.nodes["RiskFactor"][r.id] = {
                "id": r.id,
                "name_vi": r.name_vi,
                "review_status": r.review_status.value,
            }
        return len(risk_factors)

    def upsert_lab_tests(self, lab_tests: list[LabTestRecord], tx: Any = None) -> int:
        for lt in lab_tests:
            self.nodes["LabTest"][lt.id] = {
                "id": lt.id,
                "name_vi": lt.name_vi,
                "review_status": lt.review_status.value,
            }
        return len(lab_tests)

    def upsert_indicates_edges(self, edges: list[IndicatesEdge], tx: Any = None) -> int:
        for e in edges:
            if e.source_id in self.fail_on_source_ids:
                raise RuntimeError(f"Simulated error on source: {e.source_id}")
            key = (e.symptom_id, "INDICATES", e.disease_id)
            self.edges["INDICATES"][key] = {
                "weight": e.weight,
                "is_cardinal": e.is_cardinal,
                "source_id": e.source_id,
            }
        return len(edges)

    def upsert_has_risk_factor_edges(self, edges: list[HasRiskFactorEdge], tx: Any = None) -> int:
        for e in edges:
            if e.source_id in self.fail_on_source_ids:
                raise RuntimeError(f"Simulated error on source: {e.source_id}")
            key = (e.disease_id, "HAS_RISK_FACTOR", e.risk_id)
            self.edges["HAS_RISK_FACTOR"][key] = {
                "weight": e.weight,
                "source_id": e.source_id,
            }
        return len(edges)

    def upsert_confirmed_by_edges(self, edges: list[ConfirmedByEdge], tx: Any = None) -> int:
        for e in edges:
            if e.source_id in self.fail_on_source_ids:
                raise RuntimeError(f"Simulated error on source: {e.source_id}")
            key = (e.disease_id, "CONFIRMED_BY", e.lab_id)
            self.edges["CONFIRMED_BY"][key] = {
                "role": e.role.value,
                "source_id": e.source_id,
            }
        return len(edges)

    def upsert_differential_of_edges(self, edges: list[DifferentialOfEdge], tx: Any = None) -> int:
        for e in edges:
            if e.source_id in self.fail_on_source_ids:
                raise RuntimeError(f"Simulated error on source: {e.source_id}")
            key = (e.disease_id, "DIFFERENTIAL_OF", e.other_id)
            self.edges["DIFFERENTIAL_OF"][key] = {
                "distinguishing_features": e.distinguishing_features,
                "source_id": e.source_id,
            }
        return len(edges)

    def upsert_documented_in_edges(self, edges: list[DocumentedInEdge], tx: Any = None) -> int:
        for e in edges:
            if e.source_id in self.fail_on_source_ids:
                raise RuntimeError(f"Simulated error on source: {e.source_id}")
            key = (e.disease_id, "DOCUMENTED_IN", e.source_doc_id)
            self.edges["DOCUMENTED_IN"][key] = {
                "section": e.section,
                "source_id": e.source_id,
            }
        return len(edges)

    def upsert_is_a_edges(self, edges: list[IsAEdge], tx: Any = None) -> int:
        for e in edges:
            if e.source_id in self.fail_on_source_ids:
                raise RuntimeError(f"Simulated error on source: {e.source_id}")
            key = (e.child_id, "IS_A", e.parent_id)
            self.edges["IS_A"][key] = {"source_id": e.source_id}
        return len(edges)

    def upsert_superseded_by_edges(self, edges: list[SupersededByEdge], tx: Any = None) -> int:
        for e in edges:
            if e.source_id in self.fail_on_source_ids:
                raise RuntimeError(f"Simulated error on source: {e.source_id}")
            key = (e.old_id, "SUPERSEDED_BY", e.new_id)
            self.edges["SUPERSEDED_BY"][key] = {"source_id": e.source_id}
        return len(edges)

    def get_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for label, items in self.nodes.items():
            counts[label] = len(items)
        for rel_type, items in self.edges.items():
            counts[rel_type] = len(items)
        return counts

    def get_disease_count(self, tx: Any = None) -> int:
        return len(self.nodes["Disease"])

    def get_symptom_disease_frequencies(self, tx: Any = None) -> dict[str, int]:
        diseases_by_symptom: dict[str, set[str]] = {}
        for symptom_id, _, disease_id in self.edges["INDICATES"]:
            if symptom_id in self.nodes["Symptom"] and disease_id in self.nodes["Disease"]:
                diseases_by_symptom.setdefault(symptom_id, set()).add(disease_id)
        return {
            symptom_id: len(disease_ids) for symptom_id, disease_ids in diseases_by_symptom.items()
        }

    def update_symptom_idf(self, idf_by_symptom: dict[str, float], tx: Any = None) -> int:
        for symptom_id, idf in idf_by_symptom.items():
            if symptom_id in self.nodes["Symptom"]:
                self.nodes["Symptom"][symptom_id]["idf"] = idf
        return len(idf_by_symptom)
