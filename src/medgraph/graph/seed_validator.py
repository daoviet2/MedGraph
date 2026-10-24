"""Trình kiểm tra (validator) tính toàn vẹn của dữ liệu seed Knowledge Graph (F-011).

Kiểm tra:
- Trùng lặp ID trong từng loại thực thể (DUPLICATE_ID).
- Cạnh trỏ tới ID không tồn tại (DANGLING_*).
- source_id không tồn tại trong sources.csv (UNKNOWN_SOURCE_ID).
- Chu trình trong quan hệ phân cấp IS_A và SUPERSEDED_BY (CYCLE_*).
- Bệnh không có cạnh INDICATES nào (DISEASE_WITHOUT_INDICATES - error).
- Bệnh không có triệu chứng cốt lõi is_cardinal nào (DISEASE_NO_CARDINAL_SYMPTOM - warning).
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from medgraph.graph.seed_reader import SeedBundle


class IssueLevel(StrEnum):
    """Mức độ nghiêm trọng của vấn đề phát hiện được."""

    ERROR = "error"
    WARNING = "warning"


class Issue(BaseModel):
    """Mô tả một vấn đề phát hiện trong dữ liệu seed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    level: IssueLevel
    code: str
    location: str
    message: str


def find_directed_cycles(edges: list[tuple[str, str]]) -> list[list[str]]:
    """Tìm các chu trình trong danh sách cạnh có hướng (source -> target)."""
    adj: dict[str, list[str]] = {}
    for u, v in edges:
        adj.setdefault(u, []).append(v)

    visited: dict[str, int] = {}  # 0: unvisited, 1: visiting, 2: visited
    cycles: list[list[str]] = []
    path: list[str] = []

    def dfs(node: str) -> None:
        visited[node] = 1
        path.append(node)
        for neighbor in adj.get(node, []):
            if visited.get(neighbor, 0) == 1:
                idx = path.index(neighbor)
                cycles.append(path[idx:] + [neighbor])
            elif visited.get(neighbor, 0) == 0:
                dfs(neighbor)
        path.pop()
        visited[node] = 2

    for start_node in list(adj.keys()):
        if visited.get(start_node, 0) == 0:
            dfs(start_node)

    return cycles


def validate_seed_bundle(
    bundle: SeedBundle,
    only: list[str] | None = None,
) -> list[Issue]:
    """Kiểm tra toàn vẹn dữ liệu của SeedBundle và trả về danh sách Issue.

    Args:
        bundle: Gói dữ liệu SeedBundle cần kiểm tra.
        only: Danh sách các tập dữ liệu được giới hạn (nếu có).

    Returns:
        Danh sách các Issue phát hiện được.
    """
    issues: list[Issue] = []
    filter_set = set(only) if only is not None else None

    def is_active(key: str) -> bool:
        return filter_set is None or key in filter_set

    # 1. Kiểm tra trùng lặp ID trong từng loại Node
    node_collections = [
        ("sources", bundle.sources),
        ("diseases", bundle.diseases),
        ("symptoms", bundle.symptoms),
        ("risk_factors", bundle.risk_factors),
        ("lab_tests", bundle.lab_tests),
    ]

    for name, collection in node_collections:
        if not is_active(name):
            continue
        seen_ids: set[str] = set()
        for item in collection:
            if item.id in seen_ids:
                issues.append(
                    Issue(
                        level=IssueLevel.ERROR,
                        code="DUPLICATE_ID",
                        location=f"{name}.csv",
                        message=f"Trùng lặp ID '{item.id}' trong {name}.csv",
                    )
                )
            seen_ids.add(item.id)

    # Tập hợp các ID đã biết để kiểm tra tham chiếu
    source_ids = {s.id for s in bundle.sources}
    disease_ids = {d.id for d in bundle.diseases}
    symptom_ids = {s.id for s in bundle.symptoms}
    risk_ids = {r.id for r in bundle.risk_factors}
    lab_ids = {lab.id for lab in bundle.lab_tests}

    # 2. Kiểm tra source_id hợp lệ trên mọi cạnh (nếu sources được nạp)
    if is_active("sources") and source_ids:
        edge_collections = [
            ("indicates", bundle.indicates),
            ("has_risk_factors", bundle.has_risk_factors),
            ("confirmed_by", bundle.confirmed_by),
            ("differential_of", bundle.differential_of),
            ("documented_in", bundle.documented_in),
            ("is_a", bundle.is_a),
            ("superseded_by", bundle.superseded_by),
        ]
        for edge_name, edge_list in edge_collections:
            if not is_active(edge_name):
                continue
            for edge in edge_list:
                if edge.source_id not in source_ids:
                    issues.append(
                        Issue(
                            level=IssueLevel.ERROR,
                            code="UNKNOWN_SOURCE_ID",
                            location=f"edges/{edge_name}.csv",
                            message=(
                                f"source_id '{edge.source_id}' không tồn tại trong sources.csv"
                            ),
                        )
                    )

    # 3. Kiểm tra cạnh trỏ tới node không tồn tại (Dangling references)
    if is_active("indicates"):
        for edge in bundle.indicates:
            if is_active("symptoms") and edge.symptom_id not in symptom_ids:
                issues.append(
                    Issue(
                        level=IssueLevel.ERROR,
                        code="DANGLING_SYMPTOM_ID",
                        location="edges/indicates.csv",
                        message=f"symptom_id '{edge.symptom_id}' không tồn tại trong symptoms.csv",
                    )
                )
            if is_active("diseases") and edge.disease_id not in disease_ids:
                issues.append(
                    Issue(
                        level=IssueLevel.ERROR,
                        code="DANGLING_DISEASE_ID",
                        location="edges/indicates.csv",
                        message=f"disease_id '{edge.disease_id}' không tồn tại trong diseases.csv",
                    )
                )

    if is_active("has_risk_factors"):
        for edge in bundle.has_risk_factors:
            if is_active("diseases") and edge.disease_id not in disease_ids:
                issues.append(
                    Issue(
                        level=IssueLevel.ERROR,
                        code="DANGLING_DISEASE_ID",
                        location="edges/has_risk_factor.csv",
                        message=f"disease_id '{edge.disease_id}' không tồn tại trong diseases.csv",
                    )
                )
            if is_active("risk_factors") and edge.risk_id not in risk_ids:
                issues.append(
                    Issue(
                        level=IssueLevel.ERROR,
                        code="DANGLING_RISK_ID",
                        location="edges/has_risk_factor.csv",
                        message=f"risk_id '{edge.risk_id}' không tồn tại trong risk_factors.csv",
                    )
                )

    if is_active("confirmed_by"):
        for edge in bundle.confirmed_by:
            if is_active("diseases") and edge.disease_id not in disease_ids:
                issues.append(
                    Issue(
                        level=IssueLevel.ERROR,
                        code="DANGLING_DISEASE_ID",
                        location="edges/confirmed_by.csv",
                        message=f"disease_id '{edge.disease_id}' không tồn tại trong diseases.csv",
                    )
                )
            if is_active("lab_tests") and edge.lab_id not in lab_ids:
                issues.append(
                    Issue(
                        level=IssueLevel.ERROR,
                        code="DANGLING_LAB_ID",
                        location="edges/confirmed_by.csv",
                        message=f"lab_id '{edge.lab_id}' không tồn tại trong lab_tests.csv",
                    )
                )

    if is_active("differential_of"):
        for edge in bundle.differential_of:
            if is_active("diseases"):
                if edge.disease_id not in disease_ids:
                    issues.append(
                        Issue(
                            level=IssueLevel.ERROR,
                            code="DANGLING_DISEASE_ID",
                            location="edges/differential_of.csv",
                            message=(
                                f"disease_id '{edge.disease_id}' không tồn tại trong diseases.csv"
                            ),
                        )
                    )
                if edge.other_id not in disease_ids:
                    issues.append(
                        Issue(
                            level=IssueLevel.ERROR,
                            code="DANGLING_DISEASE_ID",
                            location="edges/differential_of.csv",
                            message=(
                                f"other_id '{edge.other_id}' không tồn tại trong diseases.csv"
                            ),
                        )
                    )

    if is_active("documented_in"):
        for edge in bundle.documented_in:
            if is_active("diseases") and edge.disease_id not in disease_ids:
                issues.append(
                    Issue(
                        level=IssueLevel.ERROR,
                        code="DANGLING_DISEASE_ID",
                        location="edges/documented_in.csv",
                        message=f"disease_id '{edge.disease_id}' không tồn tại trong diseases.csv",
                    )
                )
            if is_active("sources") and edge.source_doc_id not in source_ids:
                issues.append(
                    Issue(
                        level=IssueLevel.ERROR,
                        code="DANGLING_SOURCE_DOC_ID",
                        location="edges/documented_in.csv",
                        message=(
                            f"source_doc_id '{edge.source_doc_id}' không tồn tại trong sources.csv"
                        ),
                    )
                )

    if is_active("is_a"):
        for edge in bundle.is_a:
            if is_active("symptoms"):
                if edge.child_id not in symptom_ids:
                    issues.append(
                        Issue(
                            level=IssueLevel.ERROR,
                            code="DANGLING_SYMPTOM_ID",
                            location="edges/is_a.csv",
                            message=f"child_id '{edge.child_id}' không tồn tại trong symptoms.csv",
                        )
                    )
                if edge.parent_id not in symptom_ids:
                    issues.append(
                        Issue(
                            level=IssueLevel.ERROR,
                            code="DANGLING_SYMPTOM_ID",
                            location="edges/is_a.csv",
                            message=(
                                f"parent_id '{edge.parent_id}' không tồn tại trong symptoms.csv"
                            ),
                        )
                    )

    if is_active("superseded_by"):
        for edge in bundle.superseded_by:
            if is_active("sources"):
                if edge.old_id not in source_ids:
                    issues.append(
                        Issue(
                            level=IssueLevel.ERROR,
                            code="DANGLING_SOURCE_DOC_ID",
                            location="edges/superseded_by.csv",
                            message=f"old_id '{edge.old_id}' không tồn tại trong sources.csv",
                        )
                    )
                if edge.new_id not in source_ids:
                    issues.append(
                        Issue(
                            level=IssueLevel.ERROR,
                            code="DANGLING_SOURCE_DOC_ID",
                            location="edges/superseded_by.csv",
                            message=f"new_id '{edge.new_id}' không tồn tại trong sources.csv",
                        )
                    )

    # 4. Kiểm tra chu trình (Cycles) trong IS_A và SUPERSEDED_BY
    if is_active("is_a") and bundle.is_a:
        is_a_pairs = [(e.child_id, e.parent_id) for e in bundle.is_a]
        cycles = find_directed_cycles(is_a_pairs)
        for cyc in cycles:
            path_str = " -> ".join(cyc)
            issues.append(
                Issue(
                    level=IssueLevel.ERROR,
                    code="CYCLE_IS_A",
                    location="edges/is_a.csv",
                    message=f"Phát hiện chu trình phân cấp IS_A: {path_str}",
                )
            )

    if is_active("superseded_by") and bundle.superseded_by:
        sup_pairs = [(e.old_id, e.new_id) for e in bundle.superseded_by]
        cycles = find_directed_cycles(sup_pairs)
        for cyc in cycles:
            path_str = " -> ".join(cyc)
            issues.append(
                Issue(
                    level=IssueLevel.ERROR,
                    code="CYCLE_SUPERSEDED_BY",
                    location="edges/superseded_by.csv",
                    message=f"Phát hiện chu trình thay thế SUPERSEDED_BY: {path_str}",
                )
            )

    # 5. Kiểm tra bệnh: bắt buộc có cạnh INDICATES và cảnh báo nếu thiếu triệu chứng cốt lõi
    if is_active("diseases") and is_active("indicates") and bundle.diseases:
        # Nhóm triệu chứng theo bệnh
        disease_to_indicates = {}
        for edge in bundle.indicates:
            disease_to_indicates.setdefault(edge.disease_id, []).append(edge)

        for disease in bundle.diseases:
            edges = disease_to_indicates.get(disease.id, [])
            if not edges:
                issues.append(
                    Issue(
                        level=IssueLevel.ERROR,
                        code="DISEASE_WITHOUT_INDICATES",
                        location="diseases.csv",
                        message=(
                            f"Bệnh '{disease.id}' ({disease.name_vi}) không có cạnh INDICATES nào"
                        ),
                    )
                )
            else:
                has_cardinal = any(e.is_cardinal for e in edges)
                if not has_cardinal:
                    issues.append(
                        Issue(
                            level=IssueLevel.WARNING,
                            code="DISEASE_NO_CARDINAL_SYMPTOM",
                            location="diseases.csv",
                            message=(
                                f"Bệnh '{disease.id}' ({disease.name_vi}) không có triệu chứng cốt "
                                "lõi (is_cardinal=True) nào"
                            ),
                        )
                    )

    return issues
