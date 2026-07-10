"""Search orchestration helpers shared by API routes and background tasks."""
from app.extensions import db
from app.models import Cell
from app.services.ann_service import search_by_cell_index
from app.services.plot_service import search_scatter_json


def build_search_interpretation(dataset_id: int, query_cell_index: int, results: list[dict]) -> dict:
    """Build lightweight interpretation metadata for a search result set."""
    interpretation = {}
    if not results:
        return interpretation

    distances = [row["distance"] for row in results if "distance" in row]
    if distances:
        interpretation["distance_range"] = {
            "min": min(distances),
            "max": max(distances),
        }

    diseases = [row.get("disease") or "N/A" for row in results]
    age_groups = [row.get("age_group") or "N/A" for row in results]
    interpretation["disease_uniform"] = len(set(diseases)) == 1
    interpretation["age_group_uniform"] = len(set(age_groups)) == 1

    disease_dist = {}
    for disease in diseases:
        disease_dist[disease] = disease_dist.get(disease, 0) + 1
    interpretation["disease_distribution"] = disease_dist

    age_dist = {}
    for age_group in age_groups:
        age_dist[age_group] = age_dist.get(age_group, 0) + 1
    interpretation["age_group_distribution"] = age_dist

    query_cell = Cell.query.filter_by(
        dataset_id=dataset_id,
        cell_index=query_cell_index,
    ).first()
    if query_cell and query_cell.cell_type:
        same_count = sum(1 for row in results if row.get("cell_type") == query_cell.cell_type)
        interpretation["same_type_ratio"] = f"{same_count}/{len(results)} 结果与查询细胞同类型"

    return interpretation


def execute_single_search(
    dataset_id: int,
    index_id: int,
    query_cell_index: int,
    top_k: int = 10,
    filter_cell_type: str | None = None,
    max_background_points: int = 8_000,
    include_plot: bool = True,
    progress_cb=None,
    user_id: int | None = None,
) -> dict:
    """Run ANN search and build the response payload expected by the SPA."""
    if progress_cb:
        progress_cb(35, "正在执行 HNSW 检索...")

    result_data = search_by_cell_index(
        dataset_id=dataset_id,
        index_id=index_id,
        query_cell_index=query_cell_index,
        top_k=top_k,
        filter_cell_type=filter_cell_type,
        user_id=user_id,
    )
    results = result_data.get("results", [])

    if progress_cb:
        progress_cb(82, "正在生成结果解释...")

    payload = {
        "result_data": result_data,
        "interpretation": build_search_interpretation(dataset_id, query_cell_index, results),
    }
    if include_plot:
        result_cell_indices = [row["cell_index"] for row in results]
        payload["scatter_plot"] = execute_search_plot(
            dataset_id=dataset_id,
            query_cell_index=query_cell_index,
            result_cell_indices=result_cell_indices,
            max_background_points=max_background_points,
            progress_cb=progress_cb,
        )["scatter_plot"]
    return payload


def execute_search_plot(
    dataset_id: int,
    query_cell_index: int,
    result_cell_indices: list[int],
    max_background_points: int = 8_000,
    progress_cb=None,
) -> dict:
    """Build the search highlight plot independently from the ANN search result."""
    if progress_cb:
        progress_cb(25, "正在生成检索高亮图...")

    scatter_plot = search_scatter_json(
        dataset_id,
        query_cell_index,
        result_cell_indices,
        max_background_points=max_background_points,
    )

    if progress_cb:
        progress_cb(92, "正在整理图表数据...")

    return {"scatter_plot": scatter_plot}
