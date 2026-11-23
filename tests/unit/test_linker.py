"""Linker chạy với catalog và encoder giả."""

import pytest

from medgraph.config.linker import load_linker_settings
from medgraph.models.linking import CatalogEntry
from medgraph.models.schemas import Entity, EntityType
from medgraph.nlp.linker import HybridLinker

pytestmark = pytest.mark.unit


class FakeCatalog:
    def entries(self, entity_type: EntityType) -> list[CatalogEntry]:
        return [entry for entry in self.items if entry.type == entity_type]

    def parents(self, symptom_id: str) -> list[tuple[str, int]]:
        return [("parent", 2), ("parent", 1), ("grandparent", 2)]

    def __init__(self) -> None:
        self.items = [
            CatalogEntry(
                id="child",
                type=EntityType.SYMPTOM,
                name_vi="Ho ra máu",
                aliases_vi=("khạc ra máu",),
            ),
            CatalogEntry(id="other", type=EntityType.SYMPTOM, name_vi="Sốt"),
            CatalogEntry(id="risk", type=EntityType.RISK, name_vi="Hút thuốc"),
        ]


class FakeEncoder:
    calls = 0

    def encode(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [[1.0, 0.0], *([[0.0, 1.0]] * (len(texts) - 1))]


def test_exact_alias_and_negated_parents() -> None:
    encoder = FakeEncoder()
    linker = HybridLinker(FakeCatalog(), encoder, bm25_min_score=0.5, embedding_min_similarity=0.8)
    result = linker.link(Entity(text="KHAC RA MAU", type=EntityType.SYMPTOM, negated=True))
    assert result.entity.id == "child"
    assert result.method == "alias"
    assert {(p.id, p.hops, p.negated) for p in result.parents} == {
        ("parent", 1, True),
        ("grandparent", 2, True),
    }
    assert encoder.calls == 0


def test_unknown_mention_asks_for_clarification() -> None:
    linker = HybridLinker(
        FakeCatalog(), FakeEncoder(), bm25_min_score=10, embedding_min_similarity=0.8
    )
    result = linker.link(Entity(text="không xác định", type=EntityType.SYMPTOM))
    assert result.entity.id is None
    assert result.clarification


def test_type_is_scoped() -> None:
    linker = HybridLinker(
        FakeCatalog(), FakeEncoder(), bm25_min_score=10, embedding_min_similarity=0.8
    )
    result = linker.link(Entity(text="Hút thuốc", type=EntityType.RISK))
    assert result.entity.id == "risk"
    assert result.parents == ()


def test_bm25_matches_lexical_variant_before_embedding() -> None:
    encoder = FakeEncoder()
    linker = HybridLinker(FakeCatalog(), encoder, bm25_min_score=0.1, embedding_min_similarity=0.8)
    result = linker.link(Entity(text="khạc máu", type=EntityType.SYMPTOM))
    assert result.entity.id == "child"
    assert result.method == "bm25"
    assert encoder.calls == 0


def test_embedding_accepts_high_similarity() -> None:
    class SemanticEncoder:
        def encode(self, texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]]

    linker = HybridLinker(
        FakeCatalog(), SemanticEncoder(), bm25_min_score=10, embedding_min_similarity=0.8
    )
    result = linker.link(Entity(text="triệu chứng khác", type=EntityType.SYMPTOM))
    assert result.entity.id == "child"
    assert result.method == "embedding"


def test_thresholds_are_loaded_from_yaml() -> None:
    settings = load_linker_settings()
    assert settings.embedding_model == "BAAI/bge-m3"
    assert 0 < settings.embedding_min_similarity < 1
