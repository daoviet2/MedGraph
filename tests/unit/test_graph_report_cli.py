"""Kiểm tra mã thoát của CLI khi cạnh thiếu nguồn."""

from argparse import Namespace
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from medgraph.models.report import GraphHealthReport
from scripts import graph_report


@pytest.mark.unit
def test_graph_report_cli_exits_one_when_source_coverage_is_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = GraphHealthReport(
        node_counts=(),
        edge_counts=(),
        provenance_mix=(),
        total_edges=2,
        edges_with_source=1,
        source_coverage_percent=50.0,
        total_source_docs=0,
        active_source_docs=0,
        active_source_percent=0.0,
        orphan_diseases=0,
    )
    monkeypatch.setattr(graph_report, "parse_args", lambda: Namespace(json=False))
    monkeypatch.setattr(graph_report, "get_settings", lambda: SimpleNamespace(batch_size=1))
    monkeypatch.setattr(graph_report, "get_neo4j_driver", lambda _: nullcontext(object()))
    monkeypatch.setattr(graph_report, "verify_connectivity", lambda _: True)
    monkeypatch.setattr(graph_report, "Neo4jGraphRepository", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(graph_report, "build_graph_health_report", lambda _: report)

    assert graph_report.main() == 1
