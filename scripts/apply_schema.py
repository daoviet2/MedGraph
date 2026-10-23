#!/usr/bin/env python3
"""CLI script áp dụng các ràng buộc và index từ schema.cypher lên Neo4j (F-007).

Thực hiện idempotent: có thể chạy lại nhiều lần mà không gây lỗi hoặc trùng lặp schema.
"""

import sys

from medgraph.config import get_settings
from medgraph.graph.connection import get_neo4j_driver, verify_connectivity
from medgraph.graph.schema import apply_schema


def main() -> int:
    """Điểm khởi chạy CLI áp dụng schema."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    settings = get_settings()
    print(f"Kết nối tới Neo4j tại {settings.neo4j_uri} (user: {settings.neo4j_user})...")

    try:
        with get_neo4j_driver(settings) as driver:
            if not verify_connectivity(driver):
                print(
                    f"LỖI: Không thể kết nối tới cơ sở dữ liệu Neo4j tại {settings.neo4j_uri}. "
                    "Hãy đảm bảo Neo4j container đang chạy (docker compose up -d neo4j).",
                    file=sys.stderr,
                )
                return 1

            print("Đang áp dụng graph schema từ schema.cypher...")
            stats = apply_schema(driver)
            print(
                f"Áp dụng schema thành công!\n"
                f"  - Số câu lệnh đã chạy: {stats['statements_executed']}\n"
                f"  - Tổng số constraints hiện có: {stats['constraints_count']}\n"
                f"  - Tổng số indexes hiện có: {stats['indexes_count']}"
            )
            return 0
    except Exception as e:
        print(f"LỖI khi áp dụng schema: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
