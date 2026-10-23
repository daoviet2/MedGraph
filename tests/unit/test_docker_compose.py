"""Unit tests xác thực cấu hình hạ tầng Docker Compose (F-006).

Kiểm tra:
- Cấu trúc YAML và tính hợp lệ của docker-compose.yml.
- Cấu hình dịch vụ neo4j: image ghim minor version, cổng 7474/7687, auth, volumes, healthcheck.
- Cấu hình dịch vụ qdrant: nằm dưới profile 'rag'.
- Khai báo named volumes cho neo4j và qdrant.
"""

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

COMPOSE_FILE = Path(__file__).resolve().parent.parent.parent / "docker-compose.yml"


@pytest.fixture
def compose_data() -> dict:
    """Đọc và parse nội dung file docker-compose.yml."""
    assert COMPOSE_FILE.exists(), f"Không tìm thấy file: {COMPOSE_FILE}"
    content = COMPOSE_FILE.read_text(encoding="utf-8")
    data = yaml.safe_load(content)
    assert isinstance(data, dict), "docker-compose.yml không phải là dict hợp lệ"
    return data


def test_compose_structure(compose_data: dict) -> None:
    """docker-compose.yml phải chứa các phần chính: services và volumes."""
    assert "services" in compose_data
    assert "volumes" in compose_data
    assert "neo4j" in compose_data["services"]
    assert "qdrant" in compose_data["services"]


def test_neo4j_service_configuration(compose_data: dict) -> None:
    """Dịch vụ neo4j phải tuân thủ đúng yêu cầu acceptance của F-006."""
    neo4j = compose_data["services"]["neo4j"]

    # Image ghim minor version neo4j 5.x community
    image = neo4j.get("image", "")
    assert image.startswith("neo4j:5.")
    assert "community" in image

    # Cổng 7474 và 7687
    ports = neo4j.get("ports", [])
    assert any("7474:7474" in str(p) for p in ports)
    assert any("7687:7687" in str(p) for p in ports)

    # Biến môi trường NEO4J_AUTH
    env = neo4j.get("environment", {})
    assert "NEO4J_AUTH" in env
    assert "${NEO4J_USER" in env["NEO4J_AUTH"]
    assert "${NEO4J_PASSWORD" in env["NEO4J_AUTH"]

    # Named volumes
    vols = neo4j.get("volumes", [])
    assert any("neo4j_data:/data" in str(v) for v in vols)
    assert any("neo4j_logs:/logs" in str(v) for v in vols)

    # Healthcheck
    hc = neo4j.get("healthcheck", {})
    assert hc, "Dịch vụ neo4j bắt buộc phải có healthcheck"
    test_cmd = hc.get("test", [])
    test_cmd_str = " ".join(test_cmd) if isinstance(test_cmd, list) else str(test_cmd)
    assert "cypher-shell" in test_cmd_str
    assert "RETURN 1" in test_cmd_str


def test_qdrant_profile_rag(compose_data: dict) -> None:
    """Dịch vụ qdrant phải thuộc profile 'rag' để không tự khởi động ở P1."""
    qdrant = compose_data["services"]["qdrant"]
    profiles = qdrant.get("profiles", [])
    assert "rag" in profiles, "qdrant phải nằm dưới profile 'rag'"


def test_named_volumes_declared(compose_data: dict) -> None:
    """Các named volume cho data và logs phải được khai báo ở top-level."""
    volumes = compose_data.get("volumes", {})
    assert "neo4j_data" in volumes
    assert "neo4j_logs" in volumes
    assert "qdrant_data" in volumes
