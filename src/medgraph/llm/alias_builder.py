"""Sinh và lưu alias nháp từ seed bằng LLMClient được inject."""

import csv
import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from medgraph.llm.base import LLMClient
from medgraph.llm.prompts import PromptTemplate
from medgraph.models.aliases import (
    AliasBuildReport,
    AliasDraftBatch,
    AliasDraftRow,
    AliasEntity,
    normalize_alias,
)

EntityType = Literal["symptom", "disease"]

CSV_FIELDS = tuple(AliasDraftRow.model_fields)


class AliasBuildError(ValueError):
    """Seed, phản hồi LLM hoặc file nháp không đủ điều kiện để ghi."""


def _read_csv(path: Path, required: set[str]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise AliasBuildError(f"Missing required CSV columns: {path}")
        return list(reader)


def read_entities(
    seed_dir: Path,
    *,
    entity_type: EntityType | None = None,
    limit: int | None = None,
) -> list[AliasEntity]:
    """Đọc seed đã có nguồn; giới hạn áp dụng trên tổng số thực thể."""
    if limit is not None and limit < 1:
        raise AliasBuildError("limit must be positive")
    source_ids = {row["id"] for row in _read_csv(seed_dir / "sources.csv", {"id"})}
    selected: list[AliasEntity] = []
    for kind, filename in (("symptom", "symptoms.csv"), ("disease", "diseases.csv")):
        if entity_type is not None and entity_type != kind:
            continue
        rows = _read_csv(seed_dir / filename, {"id", "name_vi", "aliases_vi", "source_id"})
        for row in rows:
            source_id = row["source_id"]
            if source_id not in source_ids:
                raise AliasBuildError(f"Unknown source_id for {row['id']}: {source_id}")
            if not row["id"] or not row["name_vi"]:
                raise AliasBuildError(f"Missing id/name_vi in {filename}")
            selected.append(
                AliasEntity(
                    entity_id=row["id"],
                    entity_type=kind,
                    name_vi=row["name_vi"],
                    source_id=source_id,
                    existing_aliases=tuple(
                        alias.strip() for alias in row["aliases_vi"].split(";") if alias.strip()
                    ),
                )
            )
            if limit is not None and len(selected) >= limit:
                return selected
    return selected


def _existing_keys(path: Path) -> set[tuple[str, str]]:
    if not path.exists():
        return set()
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != CSV_FIELDS:
            raise AliasBuildError(f"Unexpected draft CSV columns: {path}")
        return {(row["entity_id"], normalize_alias(row["alias"])) for row in reader}


def _append_rows(path: Path, rows: Sequence[AliasDraftRow]) -> None:
    existed = path.exists()
    if existed and not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a" if existed else "w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n")
        if not existed:
            writer.writeheader()
        writer.writerows(row.model_dump() for row in rows)


class AliasDraftGenerator:
    """Gọi LLM theo lô, kiểm tra entity ID và chỉ thêm dòng nháp chưa có."""

    def __init__(
        self,
        client: LLMClient,
        template: PromptTemplate,
        *,
        batch_size: int,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if template.output_schema != AliasDraftBatch.__name__:
            raise AliasBuildError("Prompt output_schema must be AliasDraftBatch")
        if batch_size < 1:
            raise AliasBuildError("batch_size must be positive")
        self._client = client
        self._template = template
        self._batch_size = batch_size
        self._clock = clock or (lambda: datetime.now(UTC))

    def generate(self, entities: Sequence[AliasEntity], output_dir: Path) -> AliasBuildReport:
        """Không gọi LLM cho alias đã biết; không sửa các dòng CSV có sẵn."""
        paths = {
            "symptom": output_dir / "symptoms_draft.csv",
            "disease": output_dir / "diseases_draft.csv",
        }
        existing_keys = {kind: _existing_keys(path) for kind, path in paths.items()}
        canonical_keys = {
            entity.entity_id: {
                normalize_alias(alias) for alias in (entity.name_vi, *entity.existing_aliases)
            }
            for entity in entities
        }
        by_id = {entity.entity_id: entity for entity in entities}
        if len(by_id) != len(entities):
            raise AliasBuildError("Duplicate entity_id in input")
        pending: dict[str, list[AliasDraftRow]] = {"symptom": [], "disease": []}
        proposed = 0
        generated_at = self._clock().astimezone(UTC).isoformat(timespec="seconds")
        model = self._client.model_for_tier(self._template.model_tier)

        for offset in range(0, len(entities), self._batch_size):
            batch = entities[offset : offset + self._batch_size]
            input_json = json.dumps(
                [
                    {
                        "entity_id": entity.entity_id,
                        "entity_type": entity.entity_type,
                        "name_vi": entity.name_vi,
                        "existing_aliases": entity.existing_aliases,
                    }
                    for entity in batch
                ],
                ensure_ascii=False,
            )
            prompt = self._template.render(
                entities_json=input_json,
                output_schema_json=json.dumps(
                    AliasDraftBatch.model_json_schema(), ensure_ascii=False
                ),
            )
            result = self._client.complete_structured(
                prompt,
                AliasDraftBatch,
                model_tier=self._template.model_tier,
                temperature=0.0,
                prompt_name=self._template.name,
                prompt_version=self._template.version,
            )
            batch_ids = {entity.entity_id for entity in batch}
            for draft in result.aliases:
                proposed += 1
                if draft.entity_id not in batch_ids:
                    raise AliasBuildError(f"LLM returned unknown entity_id: {draft.entity_id}")
                entity = by_id[draft.entity_id]
                alias_norm = normalize_alias(draft.alias)
                key = (entity.entity_id, alias_norm)
                if not alias_norm or alias_norm in canonical_keys[entity.entity_id]:
                    continue
                if key in existing_keys[entity.entity_type]:
                    continue
                existing_keys[entity.entity_type].add(key)
                pending[entity.entity_type].append(
                    AliasDraftRow(
                        entity_id=entity.entity_id,
                        entity_type=entity.entity_type,
                        alias=draft.alias,
                        alias_norm=alias_norm,
                        model=model,
                        prompt_version=self._template.version,
                        generated_at=generated_at,
                        source_id=entity.source_id,
                    )
                )

        for kind, path in paths.items():
            if any(entity.entity_type == kind for entity in entities):
                _append_rows(path, pending[kind])
        return AliasBuildReport(
            entities_processed=len(entities),
            aliases_proposed=proposed,
            aliases_added=sum(len(rows) for rows in pending.values()),
        )
