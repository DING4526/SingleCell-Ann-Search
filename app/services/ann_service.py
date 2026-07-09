import time
import pathlib
import numpy as np
import hnswlib
from flask import current_app
from app.extensions import db
from app.models import AnnIndex, Cell, Dataset, QueryLog
from app.services.data_service import load_vectors


def build_hnsw_index(
    dataset_id: int,
    metric: str = "l2",
    M: int = 16,
    ef_construction: int = 200,
    ef_search: int = 100,
    progress_cb=None,
) -> AnnIndex:
    """为数据集构建 HNSW 索引并保存到磁盘。

    Args:
        dataset_id: 数据集 ID
        metric: 距离度量，'l2' 或 'cosine'
        M: HNSW 参数 M
        ef_construction: 建图 ef
        ef_search: 查询 ef
        progress_cb: 可选的进度回调 progress_cb(progress: int, message: str)
    """
    def _cb(p, msg):
        if progress_cb:
            progress_cb(p, msg)

    if metric not in ("l2", "cosine"):
        raise ValueError("metric 仅支持 l2 或 cosine")
    if M < 2:
        raise ValueError("M 必须大于等于 2")
    if ef_construction < M:
        raise ValueError("ef_construction 必须大于等于 M")
    if ef_search < 1:
        raise ValueError("ef_search 必须大于等于 1")

    dataset = db.session.get(Dataset, dataset_id)
    if not dataset or dataset.status not in ("processed", "indexed"):
        raise ValueError("数据集需要先处理才能构建索引")

    _cb(10, "正在加载向量缓存...")
    vectors = load_vectors(dataset)
    n_cells, dim = vectors.shape

    _cb(25, "正在初始化 HNSW 索引结构...")
    space = "cosine" if metric == "cosine" else "l2"
    index = hnswlib.Index(space=space, dim=dim)
    index.init_index(max_elements=n_cells, ef_construction=ef_construction, M=M)
    index.set_ef(ef_search)

    _cb(40, f"正在向索引添加 {n_cells} 个向量...")
    t0 = time.time()
    # 使用 cell_index（0..n-1）作为 hnswlib 的 label
    labels = np.arange(n_cells, dtype=np.int64)
    index.add_items(vectors, labels)
    build_time_ms = (time.time() - t0) * 1000

    # 先创建 AnnIndex 记录（building 状态），获取 index_id 用于文件名唯一性
    ann_index = AnnIndex(
        dataset_id=dataset_id,
        metric=metric,
        index_path="",
        M=M,
        ef_construction=ef_construction,
        ef_search=ef_search,
        status="building",
    )
    db.session.add(ann_index)
    db.session.commit()

    try:
        _cb(75, "向量添加完成，正在保存索引文件...")
        # 使用 index_id 保证文件名唯一，不同参数组合可共存
        index_filename = f"dataset_{dataset_id}_index_{ann_index.id}_{metric}.bin"
        index_path_full = pathlib.Path(current_app.config["INDEX_DIR"]) / index_filename
        index.save_index(str(index_path_full))

        _cb(90, "正在更新数据库记录...")
        ann_index.index_path = index_filename
        ann_index.build_time_ms = build_time_ms
        ann_index.status = "ready"

        dataset.status = "indexed"
        db.session.commit()
    except Exception:
        # 构建失败，标记索引状态为 error
        ann_index.status = "error"
        db.session.commit()
        raise

    _cb(100, "索引构建完成。")
    return ann_index


def load_hnsw_index(ann_index: AnnIndex, dim: int) -> hnswlib.Index:
    """从磁盘加载已保存的 HNSW 索引。"""
    index_path_full = pathlib.Path(current_app.config["INDEX_DIR"]) / ann_index.index_path
    if not index_path_full.exists():
        raise FileNotFoundError(f"索引文件不存在: {index_path_full}")

    space = "cosine" if ann_index.metric == "cosine" else "l2"
    index = hnswlib.Index(space=space, dim=dim)
    index.load_index(str(index_path_full), max_elements=0)
    index.set_ef(ann_index.ef_search)
    return index


def search_by_cell_index(
    dataset_id: int,
    index_id: int,
    query_cell_index: int,
    top_k: int = 10,
    filter_cell_type: str = None,
    exclude_self: bool = True,
) -> dict:
    """使用 HNSW 索引检索相似细胞。"""
    dataset = db.session.get(Dataset, dataset_id)
    ann_index = db.session.get(AnnIndex, index_id)

    if not dataset or not ann_index:
        raise ValueError("数据集或索引不存在")
    if ann_index.dataset_id != dataset_id:
        raise ValueError("索引不属于当前数据集")
    if ann_index.status != "ready":
        raise ValueError("索引尚未就绪")

    vectors = load_vectors(dataset)
    n_cells = vectors.shape[0]
    if n_cells == 0:
        raise ValueError("数据集没有可检索的向量")

    top_k = max(1, min(int(top_k), min(100, max(1, n_cells - 1 if exclude_self else n_cells))))

    if query_cell_index < 0 or query_cell_index >= n_cells:
        raise ValueError(f"query_cell_index 必须在 [0, {n_cells - 1}] 范围内")

    query_vector = vectors[query_cell_index : query_cell_index + 1]

    hnsw_index = load_hnsw_index(ann_index, vectors.shape[1])

    # 如果有过滤条件，先多取一些候选再过滤
    if filter_cell_type:
        fetch_k = max(top_k * 20, 50)
    else:
        fetch_k = top_k + (1 if exclude_self else 0)
    fetch_k = min(fetch_k, n_cells)

    t0 = time.time()
    labels, distances = hnsw_index.knn_query(query_vector, k=fetch_k)
    query_time_ms = (time.time() - t0) * 1000

    labels = labels[0].tolist()
    distances = distances[0].tolist()

    # 排除查询细胞自身
    if exclude_self:
        filtered = [(l, d) for l, d in zip(labels, distances) if l != query_cell_index]
    else:
        filtered = list(zip(labels, distances))

    candidate_indices = [int(cell_idx) for cell_idx, _ in filtered]
    cells = {}
    if candidate_indices:
        cell_rows = (
            Cell.query
            .filter(Cell.dataset_id == dataset_id, Cell.cell_index.in_(candidate_indices))
            .all()
        )
        cells = {cell.cell_index: cell for cell in cell_rows}

    # 按 cell_type 过滤
    if filter_cell_type:
        type_filtered = []
        for cell_idx, dist in filtered:
            cell = cells.get(int(cell_idx))
            if cell and cell.cell_type == filter_cell_type:
                type_filtered.append((cell_idx, dist))
            if len(type_filtered) >= top_k:
                break
        filtered = type_filtered
    else:
        filtered = filtered[:top_k]

    # 构建结果列表，附带细胞元信息
    results = []
    for rank, (cell_idx, dist) in enumerate(filtered, 1):
        cell = cells.get(int(cell_idx))
        results.append(
            {
                "rank": rank,
                "cell_id": cell.id if cell else None,
                "cell_index": cell_idx,
                "cell_name": cell.cell_name if cell else "N/A",
                "distance": round(float(dist), 6),
                "cell_type": cell.cell_type if cell else "N/A",
                "disease": cell.disease if cell else "N/A",
                "age_group": cell.age_group if cell else "N/A",
            }
        )

    # 记录查询日志
    log = QueryLog(
        dataset_id=dataset_id,
        index_id=index_id,
        query_cell_index=query_cell_index,
        top_k=top_k,
        query_time_ms=query_time_ms,
        result_count=len(results),
    )
    db.session.add(log)
    db.session.commit()

    return {
        "results": results,
        "query_time_ms": round(query_time_ms, 3),
        "query_cell_index": query_cell_index,
        "top_k": top_k,
        "filter_cell_type": filter_cell_type,
    }
