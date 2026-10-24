#!/usr/bin/env python3
"""CLI script kiểm tra tính hợp lệ và toàn vẹn của dữ liệu seed (F-011).

Sử dụng:
    python scripts/validate_seed.py [--seed-dir PATH] [--only LIST] [--strict]

Ví dụ:
    python scripts/validate_seed.py --only sources
    python scripts/validate_seed.py --seed-dir tests/fixtures/seed_mini/valid
    python scripts/validate_seed.py --strict
"""

import argparse
import sys
from pathlib import Path

from medgraph.config import get_settings
from medgraph.graph.seed_reader import read_seed
from medgraph.graph.seed_validator import IssueLevel, validate_seed_bundle


def main() -> int:
    """Điểm khởi chạy script kiểm tra dữ liệu seed."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Kiểm tra tính hợp lệ và toàn vẹn dữ liệu seed Knowledge Graph."
    )
    parser.add_argument(
        "--seed-dir",
        type=str,
        default=None,
        help="Đường dẫn thư mục dữ liệu seed (mặc định lấy từ cấu hình settings).",
    )
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        help="Danh sách tập dữ liệu cần kiểm tra, phân tách bởi dấu phẩy (vd: sources,diseases).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Chế độ nghiêm ngặt: coi các cảnh báo (warning) như lỗi (error).",
    )

    args = parser.parse_args()

    # Xác định thư mục seed
    if args.seed_dir:
        seed_path = Path(args.seed_dir)
    else:
        settings = get_settings()
        seed_path = settings.seed_dir

    if not seed_path.exists():
        print(f"LỖI: Thư mục seed không tồn tại: {seed_path}", file=sys.stderr)
        return 1

    only_list = (
        [item.strip() for item in args.only.split(",") if item.strip()] if args.only else None
    )

    print(f"Đang đọc dữ liệu seed từ: {seed_path}")
    if only_list:
        print(f"Giới hạn kiểm tra: {', '.join(only_list)}")

    try:
        bundle = read_seed(seed_path, only=only_list)
    except Exception as e:
        print(f"LỖI khi đọc dữ liệu seed: {e}", file=sys.stderr)
        return 1

    # Thống kê số lượng bản ghi đã nạp
    print("Thống kê bản ghi đã nạp:")
    print(f"  - Sources: {len(bundle.sources)}")
    print(f"  - Diseases: {len(bundle.diseases)}")
    print(f"  - Symptoms: {len(bundle.symptoms)}")
    print(f"  - Risk factors: {len(bundle.risk_factors)}")
    print(f"  - Lab tests: {len(bundle.lab_tests)}")
    print(f"  - Indicates edges: {len(bundle.indicates)}")
    print(f"  - HasRiskFactor edges: {len(bundle.has_risk_factors)}")
    print(f"  - ConfirmedBy edges: {len(bundle.confirmed_by)}")
    print(f"  - DifferentialOf edges: {len(bundle.differential_of)}")
    print(f"  - DocumentedIn edges: {len(bundle.documented_in)}")
    print(f"  - IsA edges: {len(bundle.is_a)}")
    print(f"  - SupersededBy edges: {len(bundle.superseded_by)}")

    # Thực hiện kiểm tra tính toàn vẹn
    issues = validate_seed_bundle(bundle, only=only_list)

    errors = [i for i in issues if i.level == IssueLevel.ERROR]
    warnings = [i for i in issues if i.level == IssueLevel.WARNING]

    if not issues:
        print("\n[OK] Dữ liệu seed hoàn toàn hợp lệ, không có lỗi hay cảnh báo nào.")
        return 0

    print(f"\nPhát hiện {len(issues)} vấn đề ({len(errors)} lỗi, {len(warnings)} cảnh báo):")
    for issue in issues:
        prefix = "[ERROR]" if issue.level == IssueLevel.ERROR else "[WARN]"
        print(f"  {prefix} [{issue.code}] ({issue.location}): {issue.message}")

    if errors:
        print(f"\n[FAIL] Có {len(errors)} lỗi nghiêm trọng cần khắc phục.", file=sys.stderr)
        return 1

    if warnings and args.strict:
        print(
            f"\n[FAIL] Chế độ strict: có {len(warnings)} cảnh báo được coi là lỗi.",
            file=sys.stderr,
        )
        return 1

    print(f"\n[PASS] Dữ liệu hợp lệ (kèm {len(warnings)} cảnh báo).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
