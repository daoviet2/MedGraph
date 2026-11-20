"""Xuất alias được người dùng duyệt và báo cáo số dòng theo trạng thái."""

import argparse
from pathlib import Path

from medgraph.config.settings import get_settings
from medgraph.graph.alias_catalog import AliasMergeError, merge_aliases
from medgraph.graph.seed_reader import read_seed


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge approved Vietnamese aliases")
    parser.add_argument("--seed-dir", type=Path, help="Seed directory")
    parser.add_argument("--aliases-dir", type=Path, help="Draft and approved alias directory")
    args = parser.parse_args()
    settings = get_settings()
    seed_dir = args.seed_dir or settings.seed_dir
    aliases_dir = args.aliases_dir or settings.aliases_dir

    try:
        bundle = read_seed(seed_dir, only=["sources", "symptoms", "diseases"])
        report = merge_aliases(bundle, aliases_dir)
    except (AliasMergeError, OSError, ValueError) as exc:
        parser.exit(1, f"Alias merge failed: {exc}\n")

    print(
        f"Review: {report.approved} approved, {report.rejected} rejected, "
        f"{report.pending} pending; exported {report.exported} aliases"
    )
    print(
        f"Total unique approved aliases: {report.total_approved} "
        f"({report.seed_approved} seed + {report.exported} reviewed drafts)"
    )
    if report.total_approved < settings.alias_min_approved:
        parser.exit(1, f"Need at least {settings.alias_min_approved} approved aliases\n")


if __name__ == "__main__":
    main()
