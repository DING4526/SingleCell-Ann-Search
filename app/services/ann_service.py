"""Persistent ANN index construction, loading, and cell search."""
from __future__ import annotations

import json
import pathlib
import time

import hnswlib
import numpy as np
from flask import current_app

from app.extensions import db
from app.models import AnnIndex, Cell, Dataset, QueryLog
from app.services.ann_backend_service import (
    HNSWLIB_HNSW,
    build_backend_index,
    load_backend_index,
    merge_params,
    normalize_algorithm,
    params_from_index,
)
from app.services.data_service import load_vectors


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in value)


def _index_path(filename: str) -> pathlib.Path:
    return pathlib.Path(current_app.config["INDEX_DIR"]) / filename


def build_ann_index(
    dataset_id: int,
    algorithm: str = HNSWLIB_HNSW,
    metric: str = "l2",
    params: dict | None = None,
    M: int | None = None,
    ef_construction: int | None = None,
    ef_search: int | None = None,
    source_experiment_id: int | None = None,
    source_run_id: int | None = None,
    lifecycle: str = "active",
    progress_cb=None,
) -> AnnIndex:
    """Build a persistent ANN index for one processed dataset."""

    def _cb(p, msg):
        if progress_cb:
            progress_cb(p, msg)

    algorithm = normalize_algorithm(algorithm)
    if metric not in ("l2", "cosine"):
        raise ValueError("距离度量仅支持 l2 或 cosine")
    if lifecycle not in ("candidate", "active"):
        raise ValueError("索引生命周期仅支持 candidate 或 active")

    dataset = db.session.get(Dataset, dataset_id)
    if not dataset or dataset.status not in ("processed", "indexed"):
        raise ValueError("数据集需要先完成处理才能构建 ANN 索引")

    _cb(10, "加载向量缓存...")
    vectors = load_vectors(dataset)
    n_cells, dim = vectors.shape
    merged_params = dict(params or {})
    if M is not None:
        merged_params["M"] = M
    if ef_construction is not None:
        merged_params["ef_construction"] = ef_construction
    if ef_search is not None:
        merged_params["ef_search"] = ef_search
    merged_params = merge_params(algorithm, merged_params, n_cells=n_cells, dim=dim)

    ann_index = AnnIndex(
        dataset_id=dataset_id,
        algorithm=algorithm,
        metric=metric,
        index_path="",
        preprocess_path=None,
        params_json=json.dumps(merged_params, ensure_ascii=False),
        source_experiment_id=source_experiment_id,
        source_run_id=source_run_id,
        lifecycle=lifecycle,
        M=int(merged_params.get("M", 0) or 0),
        ef_construction=int(merged_params.get("ef_construction", 0) or 0),
        ef_search=int(merged_params.get("ef_search", 0) or 0),
        status="building",
    )
    db.session.add(ann_index)
    db.session.commit()

    algorithm_name = _safe_name(algorithm)
    index_filename = f"dataset_{dataset_id}_index_{ann_index.id}_{algorithm_name}_{metric}.bin"
    preprocess_filename = None
    if algorithm == "hnswlib_rp_hnsw":
        preprocess_filename = f"dataset_{dataset_id}_index_{ann_index.id}_{algorithm_name}_preprocess.npz"
        ann_index.preprocess_path = preprocess_filename
    ann_index.index_path = index_filename
    db.session.commit()

    try:
        _cb(25, f"正在构建 {algorithm} 索引...")
        build_info = build_backend_index(
            algorithm=algorithm,
            vectors=vectors,
            metric=metric,
            index_path=_index_path(index_filename),
            preprocess_path=_index_path(preprocess_filename) if preprocess_filename else None,
            params=merged_params,
        )
        _cb(90, "保存索引元数据...")
        ann_index.params_json = json.dumps(build_info["params"], ensure_ascii=False)
        ann_index.M = int(build_info["params"].get("M", ann_index.M or 0) or 0)
        ann_index.ef_construction = int(build_info["params"].get("ef_construction", ann_index.ef_construction or 0) or 0)
        ann_index.ef_search = int(build_info["params"].get("ef_search", ann_index.ef_search or 0) or 0)
        ann_index.build_time_ms = build_info["build_time_ms"]
        ann_index.index_size_bytes = build_info["index_size_bytes"]
        ann_index.backend_version = build_info["backend_version"]
        ann_index.status = "ready"
        ann_index.error_message = None
        dataset.status = "indexed"
        db.session.commit()
    except Exception as exc:
        ann_index.status = "error"
        ann_index.error_message = str(exc)
        db.session.commit()
        raise

    _cb(100, "ANN 索引构建完成。")
    return ann_index


def build_hnsw_index(
    dataset_id: int,
    metric: str = "l2",
    M: int = 16,
    ef_construction: int = 200,
    ef_search: int = 100,
    progress_cb=None,
) -> AnnIndex:
    """Backward-compatible wrapper for the original HNSW build entrypoint."""
    return build_ann_index(
        dataset_id=dataset_id,
        algorithm=HNSWLIB_HNSW,
        metric=metric,
        M=M,
        ef_construction=ef_construction,
        ef_search=ef_search,
        progress_cb=progress_cb,
    )


def load_ann_backend(ann_index: AnnIndex, dim: int):
    """Load any supported persistent ANN index."""
    index_path = _index_path(ann_index.index_path)
    if not index_path.exists():
        raise FileNotFoundError(f"Index file does not exist: {index_path}")
    preprocess_path = _index_path(ann_index.preprocess_path) if ann_index.preprocess_path else None
    return load_backend_index(
        algorithm=normalize_algorithm(ann_index.algorithm),
        metric=ann_index.metric,
        dim=dim,
        index_path=index_path,
        preprocess_path=preprocess_path,
        params=params_from_index(ann_index),
    )


def load_hnsw_index(ann_index: AnnIndex, dim: int) -> hnswlib.Index:
    """Load a legacy hnswlib index. New code should use load_ann_backend."""
    if normalize_algorithm(ann_index.algorithm) != HNSWLIB_HNSW:
        raise ValueError("Index is not a hnswlib_hnsw index")
    loaded = load_ann_backend(ann_index, dim)
    return loaded.index


def query_ann_index(ann_index: AnnIndex, vectors: np.ndarray, query_vector: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    loaded = load_ann_backend(ann_index, vectors.shape[1])
    return loaded.query(query_vector, k)


def search_by_cell_index(
    dataset_id: int,
    index_id: int,
    query_cell_index: int,
    top_k: int = 10,
    filter_cell_type: str = None,
    exclude_self: bool = True,
    user_id: int | None = None,
) -> dict:
    """Search similar cells through the selected persistent ANN index."""
    dataset = db.session.get(Dataset, dataset_id)
    ann_index = db.session.get(AnnIndex, index_id)

    if not dataset or not ann_index:
        raise ValueError("Dataset or index does not exist")
    if ann_index.dataset_id != dataset_id:
        raise ValueError("Index does not belong to the selected dataset")
    if ann_index.status != "ready":
        raise ValueError("Index is not ready")
    if ann_index.lifecycle != "active":
        raise ValueError("Index is not active")

    vectors = load_vectors(dataset)
    n_cells = vectors.shape[0]
    if n_cells == 0:
        raise ValueError("Dataset has no searchable vectors")

    top_k = max(1, min(int(top_k), min(100, max(1, n_cells - 1 if exclude_self else n_cells))))
    if query_cell_index < 0 or query_cell_index >= n_cells:
        raise ValueError(f"query_cell_index must be in [0, {n_cells - 1}]")

    query_vector = vectors[query_cell_index : query_cell_index + 1]
    if filter_cell_type:
        fetch_k = max(top_k * 20, 50)
    else:
        fetch_k = top_k + (1 if exclude_self else 0)
    fetch_k = min(fetch_k, n_cells)

    t0 = time.perf_counter()
    labels, distances = query_ann_index(ann_index, vectors, query_vector, fetch_k)
    query_time_ms = (time.perf_counter() - t0) * 1000

    pairs = [
        (int(label), float(dist))
        for label, dist in zip(labels[0].tolist(), distances[0].tolist())
        if int(label) >= 0
    ]
    if exclude_self:
        pairs = [(label, dist) for label, dist in pairs if label != query_cell_index]

    candidate_indices = [cell_idx for cell_idx, _ in pairs]
    cells = {}
    if candidate_indices:
        cell_rows = (
            Cell.query
            .filter(Cell.dataset_id == dataset_id, Cell.cell_index.in_(candidate_indices))
            .all()
        )
        cells = {cell.cell_index: cell for cell in cell_rows}

    if filter_cell_type:
        filtered = []
        for cell_idx, dist in pairs:
            cell = cells.get(cell_idx)
            if cell and cell.cell_type == filter_cell_type:
                filtered.append((cell_idx, dist))
            if len(filtered) >= top_k:
                break
    else:
        filtered = pairs[:top_k]

    results = []
    for rank, (cell_idx, dist) in enumerate(filtered, 1):
        cell = cells.get(cell_idx)
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

    db.session.add(
        QueryLog(
            dataset_id=dataset_id,
            index_id=index_id,
            user_id=user_id,
            query_cell_index=query_cell_index,
            top_k=top_k,
            query_time_ms=query_time_ms,
            result_count=len(results),
        )
    )
    db.session.commit()

    return {
        "results": results,
        "query_time_ms": round(query_time_ms, 3),
        "query_cell_index": query_cell_index,
        "top_k": top_k,
        "filter_cell_type": filter_cell_type,
        "algorithm": normalize_algorithm(ann_index.algorithm),
    }
