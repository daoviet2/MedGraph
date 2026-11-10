"""Graph Loader nạp SeedBundle theo Unit of Work.

Tuân thủ kiến trúc và quy tắc:
- Loader nhận repository qua constructor (Dependency Injection).
- Dữ liệu được nhóm theo source_id (mỗi SourceDoc là một Unit of Work).
- Mỗi nhóm thực thi trong một transaction độc lập.
- Lỗi ở một nhóm sẽ rollback nhóm đó và báo cáo, không gây ảnh hưởng tới các nhóm khác
  và không nạp dữ liệu nửa vời.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from medgraph.graph.repository import GraphWriteRepository
from medgraph.graph.seed_reader import SeedBundle
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

logger = logging.getLogger(__name__)


@dataclass
class SourceGroup:
    """Gói dữ liệu thuộc về một tài liệu nguồn (Unit of Work)."""

    source_id: str
    source_doc: SourceDocRecord | None = None
    diseases: list[DiseaseRecord] = field(default_factory=list)
    symptoms: list[SymptomRecord] = field(default_factory=list)
    risk_factors: list[RiskFactorRecord] = field(default_factory=list)
    lab_tests: list[LabTestRecord] = field(default_factory=list)
    indicates: list[IndicatesEdge] = field(default_factory=list)
    has_risk_factors: list[HasRiskFactorEdge] = field(default_factory=list)
    confirmed_by: list[ConfirmedByEdge] = field(default_factory=list)
    differential_of: list[DifferentialOfEdge] = field(default_factory=list)
    documented_in: list[DocumentedInEdge] = field(default_factory=list)
    is_a: list[IsAEdge] = field(default_factory=list)
    superseded_by: list[SupersededByEdge] = field(default_factory=list)


@dataclass
class LoadReport:
    """Báo cáo kết quả nạp đồ thị."""

    total_sources: int = 0
    succeeded_sources: list[str] = field(default_factory=list)
    failed_sources: list[tuple[str, str]] = field(default_factory=list)
    total_nodes_upserted: int = 0
    total_edges_upserted: int = 0

    @property
    def is_success(self) -> bool:
        """Thành công hoàn toàn khi không có nhóm nguồn nào bị lỗi."""
        return len(self.failed_sources) == 0 and len(self.succeeded_sources) > 0


def group_by_source(bundle: SeedBundle) -> dict[str, SourceGroup]:
    """Nhóm toàn bộ các node và quan hệ trong SeedBundle theo source_id.

    Args:
        bundle: Đối tượng SeedBundle chứa dữ liệu seed đã được parse.

    Returns:
        Từ điển ánh xạ từ source_id tới SourceGroup tương ứng.
    """
    groups: dict[str, SourceGroup] = {}

    # 1. Khởi tạo nhóm từ các SourceDoc
    for doc in bundle.sources:
        groups[doc.id] = SourceGroup(source_id=doc.id, source_doc=doc)

    # Từ điển tra cứu nhanh cho các thực thể theo id
    disease_map = {d.id: d for d in bundle.diseases}
    symptom_map = {s.id: s for s in bundle.symptoms}
    risk_map = {r.id: r for r in bundle.risk_factors}
    lab_map = {lt.id: lt for lt in bundle.lab_tests}

    # Tập hợp các node ID đã được gán vào từng nhóm
    assigned_node_ids: dict[str, set[str]] = {s_id: set() for s_id in groups}
    globally_assigned_nodes: set[str] = set()

    def ensure_group(sid: str) -> SourceGroup:
        if sid not in groups:
            groups[sid] = SourceGroup(source_id=sid)
            assigned_node_ids[sid] = set()
        return groups[sid]

    def add_node_to_group(sid: str, node_id: str, node_type: str, node_obj: Any) -> None:
        grp = ensure_group(sid)
        if node_id not in assigned_node_ids[sid]:
            assigned_node_ids[sid].add(node_id)
            globally_assigned_nodes.add(node_id)
            if node_type == "disease":
                grp.diseases.append(node_obj)
            elif node_type == "symptom":
                grp.symptoms.append(node_obj)
            elif node_type == "risk":
                grp.risk_factors.append(node_obj)
            elif node_type == "lab":
                grp.lab_tests.append(node_obj)

    # 2. Phân loại các cạnh theo edge.source_id và gắn kèm các node liên quan
    for e in bundle.indicates:
        grp = ensure_group(e.source_id)
        grp.indicates.append(e)
        if e.symptom_id in symptom_map:
            add_node_to_group(e.source_id, e.symptom_id, "symptom", symptom_map[e.symptom_id])
        if e.disease_id in disease_map:
            add_node_to_group(e.source_id, e.disease_id, "disease", disease_map[e.disease_id])

    for e in bundle.has_risk_factors:
        grp = ensure_group(e.source_id)
        grp.has_risk_factors.append(e)
        if e.disease_id in disease_map:
            add_node_to_group(e.source_id, e.disease_id, "disease", disease_map[e.disease_id])
        if e.risk_id in risk_map:
            add_node_to_group(e.source_id, e.risk_id, "risk", risk_map[e.risk_id])

    for e in bundle.confirmed_by:
        grp = ensure_group(e.source_id)
        grp.confirmed_by.append(e)
        if e.disease_id in disease_map:
            add_node_to_group(e.source_id, e.disease_id, "disease", disease_map[e.disease_id])
        if e.lab_id in lab_map:
            add_node_to_group(e.source_id, e.lab_id, "lab", lab_map[e.lab_id])

    for e in bundle.differential_of:
        grp = ensure_group(e.source_id)
        grp.differential_of.append(e)
        if e.disease_id in disease_map:
            add_node_to_group(e.source_id, e.disease_id, "disease", disease_map[e.disease_id])
        if e.other_id in disease_map:
            add_node_to_group(e.source_id, e.other_id, "disease", disease_map[e.other_id])

    for e in bundle.documented_in:
        grp = ensure_group(e.source_id)
        grp.documented_in.append(e)
        if e.disease_id in disease_map:
            add_node_to_group(e.source_id, e.disease_id, "disease", disease_map[e.disease_id])

    for e in bundle.is_a:
        grp = ensure_group(e.source_id)
        grp.is_a.append(e)
        if e.child_id in symptom_map:
            add_node_to_group(e.source_id, e.child_id, "symptom", symptom_map[e.child_id])
        if e.parent_id in symptom_map:
            add_node_to_group(e.source_id, e.parent_id, "symptom", symptom_map[e.parent_id])

    for e in bundle.superseded_by:
        grp = ensure_group(e.source_id)
        grp.superseded_by.append(e)

    # 3. Gom các node còn lại chưa xuất hiện trong bất kỳ cạnh nào
    fallback_sid = bundle.sources[0].id if bundle.sources else "DEFAULT_SOURCE"
    hpo_sid = "SRC:HPO" if "SRC:HPO" in groups else fallback_sid

    for s_id, s_obj in symptom_map.items():
        if s_id not in globally_assigned_nodes:
            target_sid = hpo_sid if s_id.startswith("HP:") else fallback_sid
            add_node_to_group(target_sid, s_id, "symptom", s_obj)

    for d_id, d_obj in disease_map.items():
        if d_id not in globally_assigned_nodes:
            add_node_to_group(fallback_sid, d_id, "disease", d_obj)

    for r_id, r_obj in risk_map.items():
        if r_id not in globally_assigned_nodes:
            add_node_to_group(fallback_sid, r_id, "risk", r_obj)

    for l_id, l_obj in lab_map.items():
        if l_id not in globally_assigned_nodes:
            add_node_to_group(fallback_sid, l_id, "lab", l_obj)

    return groups


class GraphLoader:
    """Bộ nạp dữ liệu đồ thị tri thức đảm bảo tính nguyên tử và idempotent."""

    def __init__(self, repository: GraphWriteRepository) -> None:
        self.repository = repository

    def load(self, bundle: SeedBundle) -> LoadReport:
        """Nạp toàn bộ SeedBundle vào đồ thị tri thức.

        Nhóm dữ liệu theo source_id. Mỗi nhóm thực thi trong một transaction riêng biệt.
        Nếu nhóm bị lỗi, transaction sẽ tự động rollback mà không ảnh hưởng tới nhóm khác.

        Args:
            bundle: Đối tượng SeedBundle cần nạp.

        Returns:
            LoadReport tổng kết kết quả nạp.
        """
        groups = group_by_source(bundle)
        report = LoadReport(total_sources=len(groups))

        logger.info(f"Bắt đầu nạp {len(groups)} nhóm nguồn vào Knowledge Graph...")

        for source_id, grp in groups.items():
            try:
                with self.repository.transaction() as tx:
                    nodes_cnt = 0
                    edges_cnt = 0

                    # 1. Nạp SourceDoc
                    if grp.source_doc:
                        nodes_cnt += self.repository.upsert_source_docs([grp.source_doc], tx=tx)

                    # 2. Nạp các Node thực thể
                    if grp.diseases:
                        nodes_cnt += self.repository.upsert_diseases(grp.diseases, tx=tx)
                    if grp.symptoms:
                        nodes_cnt += self.repository.upsert_symptoms(grp.symptoms, tx=tx)
                    if grp.risk_factors:
                        nodes_cnt += self.repository.upsert_risk_factors(grp.risk_factors, tx=tx)
                    if grp.lab_tests:
                        nodes_cnt += self.repository.upsert_lab_tests(grp.lab_tests, tx=tx)

                    # 3. Nạp các Cạnh
                    if grp.indicates:
                        edges_cnt += self.repository.upsert_indicates_edges(grp.indicates, tx=tx)
                    if grp.has_risk_factors:
                        edges_cnt += self.repository.upsert_has_risk_factor_edges(
                            grp.has_risk_factors, tx=tx
                        )
                    if grp.confirmed_by:
                        edges_cnt += self.repository.upsert_confirmed_by_edges(
                            grp.confirmed_by, tx=tx
                        )
                    if grp.differential_of:
                        edges_cnt += self.repository.upsert_differential_of_edges(
                            grp.differential_of, tx=tx
                        )
                    if grp.documented_in:
                        edges_cnt += self.repository.upsert_documented_in_edges(
                            grp.documented_in, tx=tx
                        )
                    if grp.is_a:
                        edges_cnt += self.repository.upsert_is_a_edges(grp.is_a, tx=tx)
                    if grp.superseded_by:
                        edges_cnt += self.repository.upsert_superseded_by_edges(
                            grp.superseded_by, tx=tx
                        )

                report.succeeded_sources.append(source_id)
                report.total_nodes_upserted += nodes_cnt
                report.total_edges_upserted += edges_cnt
                logger.debug(
                    f"Nạp thành công nguồn {source_id}: {nodes_cnt} nodes, {edges_cnt} edges"
                )

            except Exception as exc:
                err_msg = str(exc)
                logger.error(
                    f"Thất bại khi nạp nguồn {source_id} (đã rollback transaction): {err_msg}"
                )
                report.failed_sources.append((source_id, err_msg))

        return report
