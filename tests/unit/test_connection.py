"""Unit tests cho module quản lý kết nối Neo4j (graph/connection.py) và áp schema (F-007).

Sử dụng mock để kiểm tra logic factory, context manager và kiểm tra lỗi mà không cần Neo4j thật.
"""

from unittest.mock import MagicMock, patch

import pytest
from neo4j.exceptions import ServiceUnavailable

from medgraph.config import Settings
from medgraph.graph.connection import (
    create_neo4j_driver,
    get_neo4j_driver,
    verify_connectivity,
)
from medgraph.graph.schema import apply_schema

pytestmark = pytest.mark.unit


@pytest.fixture
def test_settings() -> Settings:
    """Fixture Settings dùng cho kiểm thử."""
    return Settings(
        neo4j_uri="bolt://127.0.0.1:7687",
        neo4j_user="test_user",
        neo4j_password="test_password",
        neo4j_max_connection_lifetime=1800,
        neo4j_max_connection_pool_size=20,
    )


def test_create_neo4j_driver_uses_settings(test_settings: Settings) -> None:
    """create_neo4j_driver truyền đúng thông tin từ Settings tới GraphDatabase.driver."""
    with patch("medgraph.graph.connection.GraphDatabase.driver") as mock_driver_factory:
        mock_driver = MagicMock()
        mock_driver_factory.return_value = mock_driver

        driver = create_neo4j_driver(test_settings)
        assert driver == mock_driver

        mock_driver_factory.assert_called_once_with(
            "bolt://127.0.0.1:7687",
            auth=("test_user", "test_password"),
            max_connection_lifetime=1800,
            max_connection_pool_size=20,
        )


def test_get_neo4j_driver_context_manager_lifecycle(test_settings: Settings) -> None:
    """get_neo4j_driver tự động đóng driver (driver.close()) khi thoát context manager."""
    with patch("medgraph.graph.connection.GraphDatabase.driver") as mock_driver_factory:
        mock_driver = MagicMock()
        mock_driver_factory.return_value = mock_driver

        with get_neo4j_driver(test_settings) as d:
            assert d == mock_driver
            mock_driver.close.assert_not_called()

        mock_driver.close.assert_called_once()


def test_get_neo4j_driver_context_manager_handles_exception(test_settings: Settings) -> None:
    """get_neo4j_driver vẫn gọi close() ngay cả khi xảy ra lỗi bên trong block with."""
    with patch("medgraph.graph.connection.GraphDatabase.driver") as mock_driver_factory:
        mock_driver = MagicMock()
        mock_driver_factory.return_value = mock_driver

        with pytest.raises(RuntimeError, match="Lỗi xảy ra trong context"):
            with get_neo4j_driver(test_settings):
                raise RuntimeError("Lỗi xảy ra trong context")

        mock_driver.close.assert_called_once()


def test_verify_connectivity_success() -> None:
    """verify_connectivity trả về True khi driver.verify_connectivity() thành công."""
    mock_driver = MagicMock()
    mock_driver.verify_connectivity.return_value = None

    result = verify_connectivity(mock_driver)
    assert result is True
    mock_driver.verify_connectivity.assert_called_once()


def test_verify_connectivity_failure_returns_false() -> None:
    """verify_connectivity trả về False khi gặp ServiceUnavailable."""
    mock_driver = MagicMock()
    mock_driver.verify_connectivity.side_effect = ServiceUnavailable("Không kết nối được")

    result = verify_connectivity(mock_driver)
    assert result is False
    mock_driver.verify_connectivity.assert_called_once()


def test_verify_connectivity_raise_on_error() -> None:
    """verify_connectivity ném exception khi raise_on_error=True."""
    mock_driver = MagicMock()
    mock_driver.verify_connectivity.side_effect = ServiceUnavailable("Lỗi kết nối nghiêm trọng")

    with pytest.raises(ServiceUnavailable):
        verify_connectivity(mock_driver, raise_on_error=True)


def test_apply_schema_executes_statements_on_session() -> None:
    """apply_schema chạy từng câu lệnh Cypher và truy vấn SHOW CONSTRAINTS / SHOW INDEXES."""
    from neo4j import Driver

    mock_driver = MagicMock(spec=Driver)
    mock_session = MagicMock()
    mock_driver.session.return_value.__enter__.return_value = mock_session

    # Giả lập kết quả trả về của SHOW CONSTRAINTS và SHOW INDEXES
    mock_session.run.side_effect = [
        MagicMock(),  # stmt 1
        MagicMock(),  # stmt 2
        [MagicMock(), MagicMock()],  # SHOW CONSTRAINTS -> 2 constraints
        [MagicMock(), MagicMock(), MagicMock()],  # SHOW INDEXES -> 3 indexes
    ]

    statements = [
        "CREATE CONSTRAINT c1 IF NOT EXISTS FOR (s:Symptom) REQUIRE s.id IS UNIQUE",
        "CREATE FULLTEXT INDEX idx1 IF NOT EXISTS FOR (s:Symptom) ON EACH [s.name_vi]",
    ]

    stats = apply_schema(mock_driver, statements)

    assert stats["statements_executed"] == 2
    assert stats["constraints_count"] == 2
    assert stats["indexes_count"] == 3

    assert mock_session.run.call_count == 4
    mock_session.run.assert_any_call(statements[0])
    mock_session.run.assert_any_call(statements[1])
    mock_session.run.assert_any_call("SHOW CONSTRAINTS")
    mock_session.run.assert_any_call("SHOW INDEXES")
