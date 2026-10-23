"""Quản lý kết nối và tạo driver Neo4j.

Tuân thủ kiến trúc MedGraph:
- Factory nhận Settings và trả về Driver.
- Sử dụng context manager để đảm bảo đóng kết nối an toàn (driver.close()).
- Không sử dụng biến toàn cục (global) lưu trữ connection.
"""

import logging
from collections.abc import Generator
from contextlib import contextmanager

from neo4j import Auth, Driver, GraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from medgraph.config import Settings, get_settings

logger = logging.getLogger(__name__)


def create_neo4j_driver(settings: Settings | None = None) -> Driver:
    """Tạo đối tượng Driver Neo4j từ cấu hình Settings.

    Args:
        settings: Đối tượng Settings chứa thông tin kết nối. Nếu None, nạp từ get_settings().

    Returns:
        Đối tượng neo4j.Driver đã được cấu hình.
    """
    cfg = settings or get_settings()
    auth: Auth = (cfg.neo4j_user, cfg.neo4j_password)

    driver = GraphDatabase.driver(
        cfg.neo4j_uri,
        auth=auth,
        max_connection_lifetime=cfg.neo4j_max_connection_lifetime,
        max_connection_pool_size=cfg.neo4j_max_connection_pool_size,
    )
    return driver


@contextmanager
def get_neo4j_driver(settings: Settings | None = None) -> Generator[Driver, None, None]:
    """Context manager cung cấp Neo4j Driver và tự động đóng khi kết thúc block with.

    Args:
        settings: Đối tượng Settings cấu hình.

    Yields:
        neo4j.Driver
    """
    driver = create_neo4j_driver(settings)
    try:
        yield driver
    finally:
        driver.close()


def verify_connectivity(driver: Driver, raise_on_error: bool = False) -> bool:
    """Kiểm tra kết nối tới cơ sở dữ liệu Neo4j.

    Args:
        driver: Đối tượng Driver cần kiểm tra.
        raise_on_error: Nếu True, ném lỗi khi không kết nối được thay vì trả về False.

    Returns:
        True nếu kết nối thành công, False nếu không kết nối được.

    Raises:
        ServiceUnavailable, Neo4jError nếu raise_on_error=True và kết nối thất bại.
    """
    try:
        driver.verify_connectivity()
        return True
    except (ServiceUnavailable, Neo4jError, OSError) as e:
        logger.warning("Không thể kết nối tới Neo4j: %s", e)
        if raise_on_error:
            raise
        return False
