"""Cấu hình và fixtures cho kiểm thử tích hợp (integration tests).

Tự động bỏ qua (skip) test với thông báo rõ ràng nếu cơ sở dữ liệu Neo4j không kết nối được.
"""

from collections.abc import Generator

import pytest
from neo4j import Driver

from medgraph.config import get_settings
from medgraph.graph.connection import get_neo4j_driver, verify_connectivity


@pytest.fixture(scope="session")
def neo4j_available() -> bool:
    """Kiểm tra xem máy chủ Neo4j có sẵn sàng kết nối hay không."""
    settings = get_settings()
    try:
        with get_neo4j_driver(settings) as driver:
            return verify_connectivity(driver)
    except Exception:
        return False


@pytest.fixture(autouse=True)
def skip_if_neo4j_unavailable(request: pytest.FixtureRequest, neo4j_available: bool) -> None:
    """Tự động skip test nếu Neo4j không kết nối được."""
    if not neo4j_available:
        pytest.skip("Neo4j database không khả dụng; bỏ qua integration test.")


@pytest.fixture
def driver(neo4j_available: bool) -> Generator[Driver, None, None]:
    """Cung cấp Driver Neo4j cho từng integration test."""
    if not neo4j_available:
        pytest.skip("Neo4j database không khả dụng; bỏ qua integration test.")
    settings = get_settings()
    with get_neo4j_driver(settings) as d:
        yield d
