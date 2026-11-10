"""Unit tests cho tập dữ liệu cạnh seed (F-012).

Kiểm tra:
- data/seed/edges/indicates.csv
- data/seed/edges/has_risk_factor.csv
- data/seed/edges/confirmed_by.csv
- data/seed/edges/differential_of.csv
- data/seed/edges/documented_in.csv

Yêu cầu nghiệm thu F-012:
1. Mỗi bệnh trong 36 bệnh có >= 3 cạnh INDICATES và >= 1 cạnh is_cardinal=true.
2. 100% cạnh có source_id hợp lệ từ sources.csv.
3. confirmed_by: role thuộc {'screening', 'confirmatory'}.
4. differential_of: from_disease != to_disease, có distinguishing_features.
5. documented_in: mỗi bệnh trỏ tới ít nhất 1 tài liệu nguồn.
6. weight và confidence nằm trong khoảng [0, 1].
"""

from pathlib import Path

import pytest

from medgraph.graph.seed_reader import read_seed

SEED_DIR = Path(__file__).resolve().parents[2] / "data" / "seed"


@pytest.fixture(scope="module")
def seed_bundle():
    return read_seed(SEED_DIR)


@pytest.mark.unit
def test_all_36_diseases_have_at_least_3_indicates(seed_bundle):
    disease_ids = {d.id for d in seed_bundle.diseases}
    assert len(disease_ids) >= 36

    indicates_per_disease: dict[str, list] = {d_id: [] for d_id in disease_ids}
    for edge in seed_bundle.indicates:
        indicates_per_disease[edge.disease_id].append(edge)

    for d_id, edges in indicates_per_disease.items():
        assert len(edges) >= 3, f"Bệnh {d_id} chỉ có {len(edges)} cạnh INDICATES (< 3)"


@pytest.mark.unit
def test_all_36_diseases_have_at_least_one_cardinal_symptom(seed_bundle):
    disease_ids = {d.id for d in seed_bundle.diseases}
    cardinal_per_disease: dict[str, int] = {d_id: 0 for d_id in disease_ids}

    for edge in seed_bundle.indicates:
        if edge.is_cardinal:
            cardinal_per_disease[edge.disease_id] += 1

    for d_id, count in cardinal_per_disease.items():
        assert count >= 1, f"Bệnh {d_id} không có triệu chứng then chốt (is_cardinal=True)"


@pytest.mark.unit
def test_all_edges_have_valid_source_ids(seed_bundle):
    valid_source_ids = {s.id for s in seed_bundle.sources}
    assert len(valid_source_ids) > 0

    all_edge_lists = [
        ("indicates", seed_bundle.indicates),
        ("has_risk_factors", seed_bundle.has_risk_factors),
        ("confirmed_by", seed_bundle.confirmed_by),
        ("differential_of", seed_bundle.differential_of),
        ("documented_in", seed_bundle.documented_in),
        ("is_a", seed_bundle.is_a),
    ]

    for name, edge_list in all_edge_lists:
        for idx, edge in enumerate(edge_list):
            sid = edge.source_id
            msg = f"Cạnh {name}[{idx}] có source_id='{sid}' không có trong sources.csv"
            assert edge.source_id in valid_source_ids, msg


@pytest.mark.unit
def test_indicates_weights_and_confidence(seed_bundle):
    for edge in seed_bundle.indicates:
        assert 0.0 <= edge.weight <= 1.0, f"Weight {edge.weight} ngoài [0, 1] tại {edge}"
        assert 0.0 <= edge.confidence <= 1.0, (
            f"Confidence {edge.confidence} ngoài [0, 1] tại {edge}"
        )
        assert edge.provenance in {"curated", "auto_extracted", "reviewed"}


@pytest.mark.unit
def test_confirmed_by_roles_and_valid_references(seed_bundle):
    disease_ids = {d.id for d in seed_bundle.diseases}
    lab_test_ids = {lt.id for lt in seed_bundle.lab_tests}

    assert len(seed_bundle.confirmed_by) >= 30

    for edge in seed_bundle.confirmed_by:
        assert edge.disease_id in disease_ids
        assert edge.lab_id in lab_test_ids
        assert edge.role in {"screening", "confirmatory"}
        assert 0.0 <= edge.confidence <= 1.0


@pytest.mark.unit
def test_has_risk_factor_valid_references(seed_bundle):
    disease_ids = {d.id for d in seed_bundle.diseases}
    risk_factor_ids = {rf.id for rf in seed_bundle.risk_factors}

    assert len(seed_bundle.has_risk_factors) >= 20

    for edge in seed_bundle.has_risk_factors:
        assert edge.disease_id in disease_ids
        assert edge.risk_id in risk_factor_ids
        assert 0.0 <= edge.weight <= 1.0


@pytest.mark.unit
def test_differential_of_validity(seed_bundle):
    disease_ids = {d.id for d in seed_bundle.diseases}

    assert len(seed_bundle.differential_of) >= 10

    for edge in seed_bundle.differential_of:
        assert edge.disease_id in disease_ids
        assert edge.other_id in disease_ids
        assert edge.disease_id != edge.other_id, (
            f"Bệnh {edge.disease_id} không thể là chẩn đoán phân biệt của chính nó"
        )
        assert edge.distinguishing_features, "differential_of phải có distinguishing_features"


@pytest.mark.unit
def test_documented_in_covers_diseases(seed_bundle):
    disease_ids = {d.id for d in seed_bundle.diseases}
    source_ids = {s.id for s in seed_bundle.sources}

    covered_diseases = {edge.disease_id for edge in seed_bundle.documented_in}
    assert disease_ids.issubset(covered_diseases), (
        "Mỗi bệnh phải có ít nhất 1 tài liệu nguồn trong documented_in"
    )

    for edge in seed_bundle.documented_in:
        assert edge.source_doc_id in source_ids
        assert edge.source_id in source_ids
