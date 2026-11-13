"""Kiểm tra công thức IDF và bước hậu xử lý trên fake repository."""

import math

import pytest

from medgraph.graph.repository import FakeGraphRepository
from medgraph.graph.stats import compute_idf, refresh_symptom_idf


@pytest.mark.unit
def test_compute_idf_matches_hand_calculation_and_specificity() -> None:
    rare = compute_idf(10, 1)
    common = compute_idf(10, 5)

    assert rare == pytest.approx(math.log(5))
    assert common == pytest.approx(math.log(10 / 6))
    assert rare > common
    assert compute_idf(1, 1) == pytest.approx(math.log(0.5))


@pytest.mark.unit
def test_compute_idf_rejects_invalid_counts() -> None:
    with pytest.raises(ValueError):
        compute_idf(0, 0)
    with pytest.raises(ValueError):
        compute_idf(2, 3)


@pytest.mark.unit
def test_refresh_idf_is_repeatable_and_uses_distinct_diseases() -> None:
    repo = FakeGraphRepository()
    repo.nodes["Disease"] = {id_: {"id": id_} for id_ in ("d1", "d2", "d3")}
    repo.nodes["Symptom"] = {id_: {"id": id_} for id_ in ("rare", "common", "unlinked")}
    repo.edges["INDICATES"] = {
        ("rare", "INDICATES", "d1"): {},
        ("common", "INDICATES", "d1"): {},
        ("common", "INDICATES", "d2"): {},
    }

    assert refresh_symptom_idf(repo) == 2
    first = {id_: props.get("idf") for id_, props in repo.nodes["Symptom"].items()}
    assert first["rare"] == pytest.approx(math.log(3 / 2))
    assert first["common"] == pytest.approx(math.log(3 / 3))
    assert first["unlinked"] is None
    assert first["rare"] > first["common"]

    assert refresh_symptom_idf(repo) == 2
    assert {id_: props.get("idf") for id_, props in repo.nodes["Symptom"].items()} == first


@pytest.mark.unit
def test_refresh_idf_on_empty_graph_writes_nothing() -> None:
    assert refresh_symptom_idf(FakeGraphRepository()) == 0
