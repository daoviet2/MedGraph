"""Value Objects cho snapshot và báo cáo sức khỏe graph."""

from pydantic import BaseModel, ConfigDict


class ReportValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class NamedCount(ReportValue):
    name: str
    count: int


class GraphHealthSnapshot(ReportValue):
    node_counts: tuple[NamedCount, ...]
    edge_counts: tuple[NamedCount, ...]
    provenance_counts: tuple[NamedCount, ...]
    total_edges: int
    edges_with_source: int
    total_source_docs: int
    active_source_docs: int
    orphan_diseases: int


class ProvenanceShare(ReportValue):
    name: str
    count: int
    percent: float


class GraphHealthReport(ReportValue):
    node_counts: tuple[NamedCount, ...]
    edge_counts: tuple[NamedCount, ...]
    provenance_mix: tuple[ProvenanceShare, ...]
    total_edges: int
    edges_with_source: int
    source_coverage_percent: float
    total_source_docs: int
    active_source_docs: int
    active_source_percent: float
    orphan_diseases: int

    @property
    def has_complete_provenance(self) -> bool:
        return self.edges_with_source == self.total_edges

    def to_dict(self) -> dict[str, object]:
        """Tạo dữ liệu JSON ở ranh giới CLI."""
        return {
            "nodes": {item.name: item.count for item in self.node_counts},
            "edges": {item.name: item.count for item in self.edge_counts},
            "provenance_mix": {
                item.name: {"count": item.count, "percent": item.percent}
                for item in self.provenance_mix
            },
            "total_edges": self.total_edges,
            "edges_with_source": self.edges_with_source,
            "source_coverage_percent": self.source_coverage_percent,
            "total_source_docs": self.total_source_docs,
            "active_source_docs": self.active_source_docs,
            "active_source_percent": self.active_source_percent,
            "orphan_diseases": self.orphan_diseases,
        }
