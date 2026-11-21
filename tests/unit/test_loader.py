"""Unit tests cho GraphLoader và FakeGraphRepository (F-013).

Kiểm tra:
- Hàm group_by_source nhóm đúng các node và cạnh theo source_id.
- GraphLoader nạp thành công toàn bộ gói dữ liệu qua FakeGraphRepository.
- Tính idempotent: nạp 2 lần cho cùng một kết quả số lượng node/cạnh.
- Tính cô lập lỗi của Unit of Work: lỗi ở một source_id được rollback độc lập,
  không ảnh hưởng tới các nhóm source_id khác và không nạp nửa vời.
"""

from pathlib import Path

import pytest

from medgraph.graph.loader import GraphLoader, group_by_source
from medgraph.graph.repository import FakeGraphRepository
from medgraph.graph.seed_reader import read_seed

SEED_MINI_VALID = Path(__file__).resolve().parents[1] / "fixtures" / "seed_mini" / "valid"


@pytest.fixture
def mini_bundle():
    """Nạp SeedBundle từ fixture seed_mini/valid."""
    return read_seed(SEED_MINI_VALID)


@pytest.mark.unit
def test_group_by_source_groups_correctly(mini_bundle):
    groups = group_by_source(mini_bundle)

    # 3 nguồn trong fixture mini: SRC:BYT_2020, SRC:WHO_2022, SRC:BYT_2015
    assert len(groups) == 3
    assert "SRC:BYT_2020" in groups
    assert "SRC:WHO_2022" in groups
    assert "SRC:BYT_2015" in groups

    byt_grp = groups["SRC:BYT_2020"]
    assert byt_grp.source_doc is not None
    assert byt_grp.source_doc.id == "SRC:BYT_2020"
    assert len(byt_grp.diseases) > 0
    assert len(byt_grp.indicates) > 0
    assert {doc.id for doc in byt_grp.referenced_source_docs} == {"SRC:BYT_2015"}

    who_grp = groups["SRC:WHO_2022"]
    assert who_grp.source_doc is not None
    assert who_grp.source_doc.id == "SRC:WHO_2022"


@pytest.mark.unit
def test_graph_loader_loads_successfully_in_memory(mini_bundle):
    repo = FakeGraphRepository()
    loader = GraphLoader(repo)

    report = loader.load(mini_bundle)

    assert report.is_success is True
    assert len(report.failed_sources) == 0
    assert len(report.succeeded_sources) == 3
    assert report.total_nodes_upserted > 0
    assert report.total_edges_upserted > 0

    counts = repo.get_counts()
    assert counts["SourceDoc"] == 3
    assert counts["Disease"] == 2
    assert counts["Symptom"] == 3
    assert counts["INDICATES"] == 3


@pytest.mark.unit
def test_graph_loader_is_idempotent(mini_bundle):
    repo = FakeGraphRepository()
    loader = GraphLoader(repo)

    # Nạp lần 1
    report1 = loader.load(mini_bundle)
    assert report1.is_success is True
    counts1 = repo.get_counts()

    # Nạp lần 2 trên cùng một repository
    report2 = loader.load(mini_bundle)
    assert report2.is_success is True
    counts2 = repo.get_counts()

    # Số lượng node và cạnh phải giống hệt nhau
    assert counts1 == counts2


@pytest.mark.unit
def test_graph_loader_unit_of_work_error_isolation(mini_bundle):
    repo = FakeGraphRepository()
    # Giả lập lỗi transaction chỉ xảy ra ở nguồn SRC:WHO_2022
    repo.fail_on_source_ids.add("SRC:WHO_2022")

    loader = GraphLoader(repo)
    report = loader.load(mini_bundle)

    # Tổng thể không thành công hoàn toàn
    assert report.is_success is False

    # Nguồn lỗi được ghi nhận đúng
    failed_sids = [s_id for s_id, _ in report.failed_sources]
    assert "SRC:WHO_2022" in failed_sids

    # Nguồn không lỗi vẫn thành công
    assert "SRC:BYT_2020" in report.succeeded_sources
    assert "SRC:BYT_2015" in report.succeeded_sources

    # Dữ liệu của nguồn lỗi KHÔNG hề tồn tại trong repo (đã rollback)
    assert "SRC:WHO_2022" not in repo.nodes["SourceDoc"]
    for edge_dict in repo.edges.values():
        for props in edge_dict.values():
            assert props.get("source_id") != "SRC:WHO_2022"

    # Dữ liệu của nguồn thành công vẫn tồn tại đầy đủ
    assert "SRC:BYT_2020" in repo.nodes["SourceDoc"]
