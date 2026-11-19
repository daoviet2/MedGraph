"""Sinh file alias nháp từ seed; mặc định chỉ xem kế hoạch khi --dry-run."""

import argparse
from pathlib import Path

from medgraph.config.settings import get_settings
from medgraph.llm.alias_builder import AliasBuildError, AliasDraftGenerator, read_entities
from medgraph.llm.base import LLMError
from medgraph.llm.cache import CachedLLMClient
from medgraph.llm.factory import create_llm_client
from medgraph.llm.prompts import PromptRegistry


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate pending Vietnamese alias drafts")
    parser.add_argument("--dry-run", action="store_true", help="Count entities without calling LLM")
    parser.add_argument("--limit", type=int, help="Maximum number of entities to process")
    parser.add_argument("--entity-type", choices=("symptom", "disease"))
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")

    settings = get_settings()
    try:
        entities = read_entities(settings.seed_dir, entity_type=args.entity_type, limit=args.limit)
        if args.dry_run:
            print(f"Dry run: {len(entities)} entities would be processed; no LLM calls")
            return

        template = PromptRegistry(Path("prompts")).get("build_aliases")
        alias_settings = settings.model_copy(
            update={
                "llm_max_tokens": settings.alias_max_tokens,
                "llm_timeout_seconds": settings.alias_timeout_seconds,
                "fpt_thinking": "disabled",
            }
        )
        client = CachedLLMClient(create_llm_client(alias_settings), settings.cache_dir / "llm")
        report = AliasDraftGenerator(
            client, template, batch_size=settings.alias_batch_size
        ).generate(entities, settings.aliases_dir)
    except (AliasBuildError, LLMError) as exc:
        parser.exit(1, f"Alias build failed: {exc}\n")
    print(
        f"Processed {report.entities_processed} entities; "
        f"proposed {report.aliases_proposed} aliases; added {report.aliases_added} pending rows"
    )


if __name__ == "__main__":
    main()
