"""Unit tests cho hợp đồng dữ liệu pipeline/API (models/schemas.py)."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from medgraph.models.schemas import (
    SCHEMA_VERSION,
    Candidate,
    Citation,
    Claim,
    Entity,
    EntityType,
    Provenance,
    Result,
    ReviewStatus,
    Subgraph,
    SubgraphEdge,
    SubgraphNode,
    Urgency,
)


@pytest.mark.unit
def test_schema_version_constant() -> None:
    """Xác nhận hằng số SCHEMA_VERSION được đặt đúng phiên bản 1.0.0."""
    assert SCHEMA_VERSION == "1.0.0"


@pytest.mark.unit
def test_enum_values() -> None:
    """Xác nhận các enum y khoa có đầy đủ giá trị theo thiết kế."""
    assert set(Urgency) == {
        Urgency.EMERGENCY,
        Urgency.SEE_DOCTOR_SOON,
        Urgency.MONITOR,
        Urgency.SELF_CARE_INFO,
    }
    assert Urgency.EMERGENCY == "EMERGENCY"

    assert set(EntityType) == {
        EntityType.SYMPTOM,
        EntityType.RISK,
        EntityType.LAB,
        EntityType.DRUG,
        EntityType.CONDITION,
    }
    assert EntityType.SYMPTOM == "symptom"

    assert set(Provenance) == {
        Provenance.CURATED,
        Provenance.REVIEWED,
        Provenance.AUTO_EXTRACTED,
    }
    assert Provenance.CURATED == "curated"

    assert set(ReviewStatus) == {
        ReviewStatus.PENDING,
        ReviewStatus.APPROVED,
        ReviewStatus.REJECTED,
    }
    assert ReviewStatus.PENDING == "pending"


@pytest.mark.unit
def test_candidate_likelihood_validation() -> None:
    """Xác nhận likelihood phải nằm trong khoảng [0.0, 1.0], ngoài khoảng bị từ chối."""
    # Hợp lệ
    valid_c = Candidate(
        disease_id="ICD10:J18",
        name_vi="Viêm phổi",
        likelihood=0.75,
        danger_level=2,
    )
    assert valid_c.likelihood == 0.75

    # Biên 0.0 và 1.0 hợp lệ
    Candidate(disease_id="ICD10:J18", name_vi="Viêm phổi", likelihood=0.0, danger_level=1)
    Candidate(disease_id="ICD10:J18", name_vi="Viêm phổi", likelihood=1.0, danger_level=3)

    # Lớn hơn 1.0 bị từ chối
    with pytest.raises(ValidationError) as exc:
        Candidate(
            disease_id="ICD10:J18",
            name_vi="Viêm phổi",
            likelihood=1.2,
            danger_level=2,
        )
    assert "likelihood" in str(exc.value)

    # Nhỏ hơn 0.0 bị từ chối
    with pytest.raises(ValidationError) as exc:
        Candidate(
            disease_id="ICD10:J18",
            name_vi="Viêm phổi",
            likelihood=-0.1,
            danger_level=2,
        )
    assert "likelihood" in str(exc.value)


@pytest.mark.unit
def test_candidate_danger_level_validation() -> None:
    """Xác nhận danger_level chỉ nhận 1, 2, 3."""
    for level in [1, 2, 3]:
        c = Candidate(
            disease_id="ICD10:J18",
            name_vi="Viêm phổi",
            likelihood=0.5,
            danger_level=level,
        )
        assert c.danger_level == level

    # danger_level = 4 bị từ chối
    with pytest.raises(ValidationError) as exc:
        Candidate(
            disease_id="ICD10:J18",
            name_vi="Viêm phổi",
            likelihood=0.5,
            danger_level=4,
        )
    assert "danger_level" in str(exc.value)

    # danger_level = 0 bị từ chối
    with pytest.raises(ValidationError) as exc:
        Candidate(
            disease_id="ICD10:J18",
            name_vi="Viêm phổi",
            likelihood=0.5,
            danger_level=0,
        )
    assert "danger_level" in str(exc.value)


@pytest.mark.unit
def test_entity_duration_days_validation() -> None:
    """Xác nhận duration_days phải >= 0 nếu được cung cấp."""
    e = Entity(text="ho kéo dài", type=EntityType.SYMPTOM, duration_days=14)
    assert e.duration_days == 14

    e_zero = Entity(text="khó thở cấp", type=EntityType.SYMPTOM, duration_days=0)
    assert e_zero.duration_days == 0

    with pytest.raises(ValidationError) as exc:
        Entity(text="ho", type=EntityType.SYMPTOM, duration_days=-3)
    assert "duration_days" in str(exc.value)


@pytest.mark.unit
def test_claim_validation() -> None:
    """Xác nhận Claim text không được rỗng hoặc chỉ có khoảng trắng."""
    citation = Citation(chunk_id="chunk_1")

    valid_claim = Claim(text="Có triệu chứng sốt về chiều", citation=citation)
    assert valid_claim.text == "Có triệu chứng sốt về chiều"

    # Rỗng
    with pytest.raises(ValidationError):
        Claim(text="", citation=citation)

    # Chỉ có khoảng trắng
    with pytest.raises(ValidationError):
        Claim(text="   \t \n", citation=citation)


@pytest.mark.unit
def test_disclaimer_validation() -> None:
    """Xác nhận Result disclaimer bắt buộc không được rỗng hoặc chỉ có khoảng trắng."""
    with pytest.raises(ValidationError):
        Result(
            abstained=False,
            urgency=Urgency.MONITOR,
            disclaimer="",
        )

    with pytest.raises(ValidationError):
        Result(
            abstained=False,
            urgency=Urgency.MONITOR,
            disclaimer="   ",
        )


@pytest.mark.unit
def test_extra_fields_forbidden() -> None:
    """Xác nhận mọi model đều từ chối trường lạ (extra='forbid')."""
    with pytest.raises(ValidationError) as exc:
        Entity(text="ho", type=EntityType.SYMPTOM, unknown_field="test")
    assert "extra_forbidden" in str(exc.value)

    with pytest.raises(ValidationError) as exc:
        Citation(chunk_id="c1", random_attr=123)
    assert "extra_forbidden" in str(exc.value)

    with pytest.raises(ValidationError) as exc:
        Candidate(
            disease_id="ICD10:J18",
            name_vi="Viêm phổi",
            likelihood=0.5,
            danger_level=2,
            unexpected="fail",
        )
    assert "extra_forbidden" in str(exc.value)

    with pytest.raises(ValidationError) as exc:
        Result(
            abstained=False,
            urgency=Urgency.MONITOR,
            disclaimer="Disclaimer",
            extra_result_field=True,
        )
    assert "extra_forbidden" in str(exc.value)

    with pytest.raises(ValidationError) as exc:
        SubgraphNode(id="n1", label="Symptom", name="ho", extra_prop=1)
    assert "extra_forbidden" in str(exc.value)

    with pytest.raises(ValidationError) as exc:
        SubgraphEdge(source="n1", target="n2", type="INDICATES", invalid_field="err")
    assert "extra_forbidden" in str(exc.value)


@pytest.mark.unit
def test_subgraph_construction() -> None:
    """Xác nhận cấu trúc Subgraph, SubgraphNode và SubgraphEdge hoạt động đúng."""
    node1 = SubgraphNode(id="HP:0012735", label="Symptom", name="ho dai dẳng")
    node2 = SubgraphNode(id="ICD10:A15", label="Disease", name="Lao phổi")
    edge = SubgraphEdge(source="HP:0012735", target="ICD10:A15", type="INDICATES", weight=0.85)

    subgraph = Subgraph(nodes=[node1, node2], edges=[edge])
    assert len(subgraph.nodes) == 2
    assert len(subgraph.edges) == 1
    assert subgraph.edges[0].type == "INDICATES"
    assert subgraph.edges[0].weight == 0.85


@pytest.mark.unit
def test_models_are_frozen() -> None:
    """Xác nhận các model Pydantic là bất biến (frozen=True)."""
    entity = Entity(text="sốt nhẹ", type=EntityType.SYMPTOM)
    with pytest.raises(ValidationError):
        entity.negated = True  # type: ignore[misc]

    candidate = Candidate(
        disease_id="ICD10:J18",
        name_vi="Viêm phổi",
        likelihood=0.5,
        danger_level=2,
    )
    with pytest.raises(ValidationError):
        candidate.likelihood = 0.9  # type: ignore[misc]


@pytest.mark.unit
def test_parse_and_roundtrip_canonical_example() -> None:
    """Xác nhận file JSON ví dụ canonical parse thành công và round-trip không mất dữ liệu."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "result_example.json"
    assert fixture_path.exists(), f"Không tìm thấy fixture {fixture_path}"

    raw_json = fixture_path.read_text(encoding="utf-8")
    result = Result.model_validate_json(raw_json)

    # Kiểm tra các trường chính
    assert result.schema_version == "1.0.0"
    assert result.abstained is False
    assert result.urgency == Urgency.SEE_DOCTOR_SOON
    assert len(result.entities) == 1
    assert result.entities[0].text == "ho dai dẳng"
    assert result.entities[0].id == "HP:0012735"
    assert result.entities[0].duration_days == 21
    assert result.entities[0].type == EntityType.SYMPTOM

    assert len(result.likely) == 1
    assert result.likely[0].disease_id == "ICD10:A15"
    assert result.likely[0].name_vi == "Lao phổi"
    assert result.likely[0].likelihood == 0.82
    assert result.likely[0].danger_level == 3
    assert result.likely[0].claims[0].citation.supported is True

    assert len(result.cant_miss) == 1
    assert result.cant_miss[0].disease_id == "ICD10:I26"
    assert result.cant_miss[0].cant_miss is True

    assert len(result.subgraph.nodes) == 2
    assert len(result.subgraph.edges) == 1
    assert result.subgraph.edges[0].type == "INDICATES"
    assert result.subgraph.edges[0].weight == 0.85

    assert "MedGraph là công cụ tham khảo" in result.disclaimer

    # Round-trip serialization
    dumped_json = result.model_dump_json()
    reloaded = Result.model_validate_json(dumped_json)
    assert reloaded == result
    assert json.loads(dumped_json) == json.loads(raw_json)
