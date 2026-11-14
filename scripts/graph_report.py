#!/usr/bin/env python3
"""In báo cáo sức khỏe Knowledge Graph và tùy chọn lưu JSON."""

import argparse
import json
import sys
from pathlib import Path

from neo4j.exceptions import Neo4jError, ServiceUnavailable

from medgraph.config import get_settings
from medgraph.graph.connection import get_neo4j_driver, verify_connectivity
from medgraph.graph.report import build_graph_health_report
from medgraph.graph.repository import Neo4jGraphRepository
from medgraph.models.report import GraphHealthReport

REPORT_PATH = Path("reports/graph_report.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Báo cáo sức khỏe Knowledge Graph MedGraph.")
    parser.add_argument(
        "--json", action="store_true", help="Ghi báo cáo vào reports/graph_report.json."
    )
    return parser.parse_args()


def print_report(report: GraphHealthReport) -> None:
    print("=== MEDGRAPH: BÁO CÁO SỨC KHỎE GRAPH ===")
    print("Nodes theo label:")
    for item in report.node_counts:
        print(f"  {item.name:<20} {item.count:>6}")
    print("Cạnh theo type:")
    for item in report.edge_counts:
        print(f"  {item.name:<20} {item.count:>6}")
    print("Provenance mix:")
    for item in report.provenance_mix:
        print(f"  {item.name:<20} {item.count:>6}  {item.percent:>6.1f}%")
    print(
        f"Cạnh có source_id: {report.edges_with_source}/{report.total_edges} "
        f"({report.source_coverage_percent:.1f}%)"
    )
    print(
        f"SourceDoc active: {report.active_source_docs}/{report.total_source_docs} "
        f"({report.active_source_percent:.1f}%)"
    )
    print(f"Bệnh không có INDICATES: {report.orphan_diseases}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    args = parse_args()
    try:
        settings = get_settings()
        with get_neo4j_driver(settings) as driver:
            if not verify_connectivity(driver):
                print("LỖI: Neo4j không khả dụng.", file=sys.stderr)
                return 1
            repository = Neo4jGraphRepository(driver, batch_size=settings.batch_size)
            report = build_graph_health_report(repository)
    except (Neo4jError, ServiceUnavailable, OSError) as exc:
        print(f"LỖI khi đọc Neo4j: {exc}", file=sys.stderr)
        return 1

    print_report(report)
    if args.json:
        try:
            REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
            REPORT_PATH.write_text(
                json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            print(f"LỖI khi ghi {REPORT_PATH}: {exc}", file=sys.stderr)
            return 1
        print(f"Đã ghi JSON: {REPORT_PATH}")
    if not report.has_complete_provenance:
        print("LỖI: Độ phủ source_id dưới 100%.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
