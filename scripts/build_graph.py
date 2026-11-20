#!/usr/bin/env python3
"""CLI script xây dựng Knowledge Graph hoàn chỉnh cho MedGraph (F-013).

Quy trình thực hiện:
1. Đọc dữ liệu seed từ --seed-dir.
2. Kiểm tra toàn vẹn tham chiếu (validate_seed); nếu có lỗi ERROR -> dừng ngay lập tức.
3. Nếu cờ --dry-run được bật: in thống kê nhóm và kết thúc mà không kết nối Neo4j.
4. Kết nối Neo4j, áp dụng các ràng buộc và index từ schema.cypher (idempotent).
5. Nạp dữ liệu qua GraphLoader theo từng nhóm SourceDoc (mỗi nhóm một transaction).
6. In báo cáo tổng kết và số lượng bản ghi đồ thị sau khi nạp.
"""

import argparse
import sys
from pathlib import Path

from medgraph.config import get_settings
from medgraph.graph.connection import get_neo4j_driver, verify_connectivity
from medgraph.graph.loader import GraphLoader, group_by_source
from medgraph.graph.repository import Neo4jGraphRepository
from medgraph.graph.schema import apply_schema
from medgraph.graph.seed_reader import read_seed
from medgraph.graph.seed_validator import IssueLevel, validate_seed_bundle
from medgraph.graph.stats import refresh_symptom_idf


def parse_args() -> argparse.Namespace:
    """Xử lý tham số dòng lệnh CLI."""
    parser = argparse.ArgumentParser(
        description="Xây dựng Knowledge Graph MedGraph từ dữ liệu seed."
    )
    parser.add_argument(
        "--seed-dir",
        type=Path,
        default=None,
        help="Đường dẫn thư mục chứa dữ liệu seed (mặc định nạp từ cấu hình Settings).",
    )
    parser.add_argument(
        "--aliases-dir",
        type=Path,
        default=None,
        help="Thư mục alias đã duyệt; mặc định dùng cấu hình khi nạp seed chính.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chỉ kiểm tra validate và phân nhóm nguồn, không kết nối và không ghi vào Neo4j.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Coi các cảnh báo (warnings) như lỗi (errors) khi validate seed.",
    )
    return parser.parse_args()


def main() -> int:
    """Hàm thực thi chính của CLI build_graph."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    args = parse_args()
    settings = get_settings()
    seed_path = args.seed_dir or settings.seed_dir

    print("=== MEDGRAPH: XÂY DỰNG KNOWLEDGE GRAPH ===")
    print(f"Thư mục dữ liệu seed: {seed_path}")

    if not seed_path.exists():
        print(f"LỖI: Thư mục seed không tồn tại: {seed_path}", file=sys.stderr)
        return 1

    # 1. Đọc dữ liệu seed
    try:
        aliases_path = args.aliases_dir or (settings.aliases_dir if args.seed_dir is None else None)
        bundle = read_seed(seed_path, aliases_dir=aliases_path)
    except Exception as exc:
        print(f"LỖI khi đọc dữ liệu seed: {exc}", file=sys.stderr)
        return 1

    # 2. Kiểm tra tính toàn vẹn (validate_seed)
    print("Đang kiểm tra tính toàn vẹn của dữ liệu seed...")
    issues = validate_seed_bundle(bundle)
    errors = [i for i in issues if i.level == IssueLevel.ERROR]
    warnings = [i for i in issues if i.level == IssueLevel.WARNING]

    if warnings:
        print(f"Cảnh báo ({len(warnings)}):")
        for w in warnings:
            print(f"  - [{w.code}] {w.location}: {w.message}")

    if errors or (warnings and args.strict):
        total_fail = len(errors) + (len(warnings) if args.strict else 0)
        print(
            f"\n[DỪNG] Phát hiện {total_fail} lỗi/cảnh báo strict trong dữ liệu seed:",
            file=sys.stderr,
        )
        for err in errors:
            print(f"  - [ERROR] [{err.code}] {err.location}: {err.message}", file=sys.stderr)
        if args.strict:
            for w in warnings:
                print(f"  - [STRICT-WARN] [{w.code}] {w.location}: {w.message}", file=sys.stderr)
        return 1

    print("[OK] Dữ liệu seed hoàn toàn hợp lệ.")

    # 3. Phân nhóm theo source_id
    groups = group_by_source(bundle)
    print(f"Đã phân nhóm thành {len(groups)} gói Unit of Work theo source_id.")

    if args.dry_run:
        print("\n[DRY RUN] Đã hoàn thành bước kiểm tra và phân nhóm dữ liệu seed.")
        print("Chi tiết các nhóm nguồn:")
        for s_id, grp in groups.items():
            total_edges = (
                len(grp.indicates)
                + len(grp.has_risk_factors)
                + len(grp.confirmed_by)
                + len(grp.differential_of)
                + len(grp.documented_in)
                + len(grp.is_a)
                + len(grp.superseded_by)
            )
            print(
                f"  - {s_id}: {len(grp.diseases)} diseases, {len(grp.symptoms)} symptoms, "
                f"{len(grp.risk_factors)} risks, {len(grp.lab_tests)} labs, {total_edges} edges"
            )
        return 0

    # 4. Kết nối Neo4j
    print(f"\nKết nối tới Neo4j tại {settings.neo4j_uri}...")
    try:
        with get_neo4j_driver(settings) as driver:
            if not verify_connectivity(driver):
                print(
                    f"LỖI: Không thể kết nối tới cơ sở dữ liệu Neo4j tại {settings.neo4j_uri}. "
                    "Hãy khởi động container bằng lệnh 'docker compose up -d neo4j'.",
                    file=sys.stderr,
                )
                return 1

            # 5. Áp dụng schema (idempotent)
            print("Đang áp dụng schema constraints và indexes...")
            stats = apply_schema(driver)
            print(
                f"  [OK] Schema áp dụng xong: {stats['constraints_count']} constraints, "
                f"{stats['indexes_count']} indexes"
            )

            # 6. Nạp dữ liệu qua GraphLoader
            repo = Neo4jGraphRepository(driver, batch_size=settings.batch_size)
            loader = GraphLoader(repo)

            print("Đang nạp các nhóm nguồn vào đồ thị (mỗi nhóm một transaction)...")
            report = loader.load(bundle)

            print("\n=== KẾT QUẢ NẠP GRAPH ===")
            print(f"Tổng số nhóm nguồn: {report.total_sources}")
            print(f"  - Thành công: {len(report.succeeded_sources)}")
            print(f"  - Thất bại:   {len(report.failed_sources)}")

            if report.failed_sources:
                print("\nDanh sách nguồn bị lỗi:", file=sys.stderr)
                for s_id, err in report.failed_sources:
                    print(f"  - {s_id}: {err}", file=sys.stderr)
                return 1

            # 7. Tính IDF từ graph đã nạp thành công, không dùng số liệu seed giả định.
            updated_symptoms = refresh_symptom_idf(repo)
            print(f"Đã tính IDF cho {updated_symptoms} triệu chứng có cạnh INDICATES.")

            # 8. Thống kê số lượng node và cạnh thực tế trên DB
            counts = repo.get_counts()
            print("\nThống kê bản ghi trên Knowledge Graph hiện tại:")
            print("  --- Nodes ---")
            for label in ["SourceDoc", "Disease", "Symptom", "RiskFactor", "LabTest"]:
                print(f"    {label}: {counts.get(label, 0)}")
            print("  --- Relationships ---")
            for rel in [
                "INDICATES",
                "HAS_RISK_FACTOR",
                "CONFIRMED_BY",
                "DIFFERENTIAL_OF",
                "DOCUMENTED_IN",
                "IS_A",
                "SUPERSEDED_BY",
            ]:
                print(f"    {rel}: {counts.get(rel, 0)}")

            print("\n[THÀNH CÔNG] Toàn bộ dữ liệu seed đã được nạp thành công vào Neo4j!")
            return 0

    except Exception as exc:
        print(f"LỖI hệ thống khi nạp graph: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
