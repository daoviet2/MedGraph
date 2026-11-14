"""Tính các tỷ lệ cho báo cáo sức khỏe Knowledge Graph."""

from typing import Any, Protocol

from medgraph.models.report import GraphHealthReport, GraphHealthSnapshot, ProvenanceShare


class GraphHealthRepository(Protocol):
    def read_graph_health(self, tx: Any = None) -> GraphHealthSnapshot: ...


def _percent(numerator: int, denominator: int, *, empty: float = 0.0) -> float:
    return 100.0 * numerator / denominator if denominator else empty


def build_graph_health_report(
    repository: GraphHealthRepository, tx: Any = None
) -> GraphHealthReport:
    """Chuyển snapshot của repository thành báo cáo có tỷ lệ phần trăm."""
    snapshot = repository.read_graph_health(tx=tx)
    return GraphHealthReport(
        node_counts=snapshot.node_counts,
        edge_counts=snapshot.edge_counts,
        provenance_mix=tuple(
            ProvenanceShare(
                name=item.name,
                count=item.count,
                percent=_percent(item.count, snapshot.total_edges),
            )
            for item in snapshot.provenance_counts
        ),
        total_edges=snapshot.total_edges,
        edges_with_source=snapshot.edges_with_source,
        source_coverage_percent=_percent(
            snapshot.edges_with_source, snapshot.total_edges, empty=100.0
        ),
        total_source_docs=snapshot.total_source_docs,
        active_source_docs=snapshot.active_source_docs,
        active_source_percent=_percent(snapshot.active_source_docs, snapshot.total_source_docs),
        orphan_diseases=snapshot.orphan_diseases,
    )
