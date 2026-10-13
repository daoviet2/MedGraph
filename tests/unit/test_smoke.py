"""Kiểm tra khởi tạo và smoke test cho medgraph."""

import pytest

import medgraph


@pytest.mark.unit
def test_medgraph_import_and_version() -> None:
    """Xác nhận package medgraph import được và có __version__ hợp lệ."""
    assert hasattr(medgraph, "__version__")
    assert medgraph.__version__ == "0.1.0"
