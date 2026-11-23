"""Link mention sang graph bằng alias, BM25 và embedding."""

import math
import re
from collections import Counter
from collections.abc import Sequence
from typing import Protocol

from medgraph.models.aliases import normalize_alias
from medgraph.models.linking import CatalogEntry, LinkedMention, ParentLink
from medgraph.models.schemas import Entity, EntityType


class Catalog(Protocol):
    def entries(self, entity_type: EntityType) -> Sequence[CatalogEntry]: ...

    def parents(self, symptom_id: str) -> Sequence[tuple[str, int]]: ...


class Encoder(Protocol):
    def encode(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


class BgeM3Encoder:
    """Adapter cho model đa ngữ, chỉ tải model khi thực sự cần embedding."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model = None

    def encode(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model.encode(list(texts))


class HybridLinker:
    def __init__(
        self,
        catalog: Catalog,
        encoder: Encoder,
        *,
        bm25_min_score: float,
        embedding_min_similarity: float,
    ) -> None:
        if bm25_min_score < 0 or not 0 <= embedding_min_similarity <= 1:
            raise ValueError("Invalid linker thresholds")
        self.catalog = catalog
        self.encoder = encoder
        self.bm25_min_score = bm25_min_score
        self.embedding_min_similarity = embedding_min_similarity

    def link(self, entity: Entity) -> LinkedMention:
        if entity.id is not None:
            raise ValueError("Linker expects an unlinked entity")
        entries = self.catalog.entries(entity.type)
        normalized = normalize_alias(entity.text)
        matches = [
            entry
            for entry in entries
            if normalized in {normalize_alias(term) for term in (entry.name_vi, *entry.aliases_vi)}
        ]
        method = "alias"
        if len(matches) != 1:
            matches = self._bm25(normalized, entries)
            method = "bm25"
        if len(matches) != 1:
            matches = self._embedding(normalized, entries)
            method = "embedding"
        if len(matches) != 1:
            return LinkedMention(
                entity=entity,
                clarification=f"Bạn có thể mô tả rõ hơn “{entity.text}” không?",
            )
        matched = matches[0]
        linked = entity.model_copy(update={"id": matched.id})
        parents = ()
        if entity.type == EntityType.SYMPTOM:
            shortest: dict[str, int] = {}
            for parent_id, hops in self.catalog.parents(matched.id):
                if parent_id != matched.id and 1 <= hops <= 2:
                    shortest[parent_id] = min(hops, shortest.get(parent_id, hops))
            parents = tuple(
                ParentLink(id=parent_id, hops=hops, negated=entity.negated)
                for parent_id, hops in sorted(shortest.items())
            )
        return LinkedMention(entity=linked, method=method, parents=parents)

    def _bm25(self, query: str, entries: Sequence[CatalogEntry]) -> list[CatalogEntry]:
        tokens = re.findall(r"\w+", query)
        documents = [
            [
                re.findall(r"\w+", normalize_alias(term))
                for term in (entry.name_vi, *entry.aliases_vi)
            ]
            for entry in entries
        ]
        flattened = [[token for term in terms for token in term] for terms in documents]
        if not tokens or not flattened:
            return []
        average_length = sum(map(len, flattened)) / len(flattened)
        frequencies = Counter(token for doc in flattened for token in set(doc))
        scores = []
        for doc in flattened:
            counts = Counter(doc)
            length_factor = 0.25 + 0.75 * len(doc) / average_length
            score = sum(
                math.log(
                    1 + (len(flattened) - frequencies[token] + 0.5) / (frequencies[token] + 0.5)
                )
                * counts[token]
                * 2.2
                / (counts[token] + 1.2 * length_factor)
                for token in tokens
                if counts[token]
            )
            scores.append(score)
        best = max(scores)
        return (
            [entry for entry, score in zip(entries, scores, strict=True) if score == best]
            if best >= self.bm25_min_score
            else []
        )

    def _embedding(self, query: str, entries: Sequence[CatalogEntry]) -> list[CatalogEntry]:
        if not entries:
            return []
        texts = [query, *(entry.name_vi for entry in entries)]
        vectors = self.encoder.encode(texts)
        query_vector = vectors[0]
        query_norm = math.sqrt(sum(value * value for value in query_vector))
        scores = []
        for vector in vectors[1:]:
            vector_norm = math.sqrt(sum(value * value for value in vector))
            denominator = query_norm * vector_norm
            score = (
                sum(a * b for a, b in zip(query_vector, vector, strict=True)) / denominator
                if denominator
                else 0.0
            )
            scores.append(score)
        best = max(scores)
        return (
            [entry for entry, score in zip(entries, scores, strict=True) if score == best]
            if best >= self.embedding_min_similarity
            else []
        )
