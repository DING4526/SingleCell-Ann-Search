"""Joint multi-dataset index construction, search, and visualization."""
import pathlib
import time

import anndata as ad
import hnswlib
import numpy as np
import pandas as pd
import scanpy as sc
import scanpy.external as sce
import plotly.graph_objects as go
from flask import current_app

from app.extensions import db
from app.models import Cell, Dataset, JointIndex, JointIndexDataset, JointQueryLog
from app.services.plot_service import (
    _apply_dark_layout,
    _build_color_map,
    _fig_to_plotly_json,
    _legend_dimension,
    _muted_color,
)


def _cb(progress_cb, progress: int, message: str):
    if progress_cb:
        progress_cb(progress, message)


def _index_file(filename: str) -> pathlib.Path:
    return pathlib.Path(current_app.config["INDEX_DIR"]) / filename


def _cache_file(filename: str) -> pathlib.Path:
    return pathlib.Path(current_app.config["CACHE_DIR"]) / filename


def _read_gene_set(dataset: Dataset) -> set[str]:
    adata = sc.read_h5ad(dataset.file_path, backed="r")
    try:
        return set(map(str, adata.var_names))
    finally:
        if getattr(adata, "isbacked", False):
            adata.file.close()


def _select_compatible_group(datasets: list[Dataset], min_common_genes: int) -> tuple[list[Dataset], list[dict], list[str]]:
    infos = []
    for position, dataset in enumerate(datasets):
        genes = _read_gene_set(dataset)
        infos.append({
            "dataset": dataset,
            "genes": genes,
            "position": position,
        })

    infos.sort(key=lambda item: (-len(item["genes"]), item["position"]))
    if not infos:
        return [], [], []

    included = [infos[0]]
    common_genes = set(infos[0]["genes"])
    skipped = []

    for info in infos[1:]:
        candidate_common = common_genes & info["genes"]
        if len(candidate_common) >= min_common_genes:
            included.append(info)
            common_genes = candidate_common
        else:
            dataset = info["dataset"]
            skipped.append({
                "dataset_id": dataset.id,
                "dataset_name": dataset.name,
                "reason": f"共同基因数不足：{len(candidate_common)} < {min_common_genes}",
            })

    included_datasets = [info["dataset"] for info in included]
    return included_datasets, skipped, sorted(common_genes)


def _load_dataset_subset(dataset: Dataset, common_genes: list[str]) -> ad.AnnData:
    adata = sc.read_h5ad(dataset.file_path)
    subset = adata[:, common_genes].copy()
    cell_indices = np.arange(subset.n_obs, dtype=np.int64)
    subset.obs = pd.DataFrame({
        "_dataset_id": str(dataset.id),
        "_cell_index": cell_indices,
    }, index=[f"{dataset.id}:{idx}" for idx in cell_indices])
    return subset


def _load_mapping(joint_index: JointIndex) -> tuple[np.ndarray, np.ndarray]:
    mapping_path = _cache_file(joint_index.mapping_path)
    mapping = np.load(str(mapping_path))
    return mapping["dataset_ids"].astype(np.int64), mapping["cell_indices"].astype(np.int64)


def _load_vectors(joint_index: JointIndex) -> np.ndarray:
    return np.load(str(_cache_file(joint_index.vector_path)))


def _load_umap(joint_index: JointIndex) -> np.ndarray:
    return np.load(str(_cache_file(joint_index.umap_path)))


def _load_hnsw(joint_index: JointIndex, dim: int) -> hnswlib.Index:
    space = "cosine" if joint_index.metric == "cosine" else "l2"
    index = hnswlib.Index(space=space, dim=dim)
    index.load_index(str(_index_file(joint_index.index_path)), max_elements=0)
    index.set_ef(joint_index.ef_search)
    return index


def _cell_info_map(dataset_ids: np.ndarray, cell_indices: np.ndarray) -> dict[tuple[int, int], Cell]:
    grouped = {}
    for dataset_id, cell_index in zip(dataset_ids.tolist(), cell_indices.tolist()):
        grouped.setdefault(int(dataset_id), set()).add(int(cell_index))

    cells = {}
    for dataset_id, indices in grouped.items():
        rows = Cell.query.filter(
            Cell.dataset_id == dataset_id,
            Cell.cell_index.in_(list(indices)),
        ).all()
        for cell in rows:
            cells[(cell.dataset_id, cell.cell_index)] = cell
    return cells


def joint_index_to_dict(joint_index: JointIndex, include_datasets: bool = True) -> dict:
    data = {
        "id": joint_index.id,
        "name": joint_index.name,
        "metric": joint_index.metric,
        "M": joint_index.M,
        "ef_construction": joint_index.ef_construction,
        "ef_search": joint_index.ef_search,
        "n_pcs": joint_index.n_pcs,
        "n_top_genes": joint_index.n_top_genes,
        "min_common_genes": joint_index.min_common_genes,
        "common_gene_count": joint_index.common_gene_count,
        "n_cells": joint_index.n_cells,
        "build_time_ms": joint_index.build_time_ms,
        "status": joint_index.status,
        "error_message": joint_index.error_message,
        "owner_id": joint_index.owner_id,
        "created_at": joint_index.created_at.isoformat() if joint_index.created_at else None,
    }
    if include_datasets:
        data["datasets"] = [
            {
                "dataset_id": row.dataset_id,
                "dataset_name": row.dataset.name if row.dataset else None,
                "status": row.status,
                "n_cells": row.n_cells,
                "skip_reason": row.skip_reason,
            }
            for row in joint_index.datasets
        ]
    return data


def build_joint_index(
    name: str,
    dataset_ids: list[int],
    metric: str = "l2",
    M: int = 16,
    ef_construction: int = 200,
    ef_search: int = 100,
    n_pcs: int = 50,
    n_top_genes: int = 2000,
    min_common_genes: int = 500,
    owner_id: int | None = None,
    progress_cb=None,
) -> JointIndex:
    if metric not in ("l2", "cosine"):
        raise ValueError("metric 仅支持 l2 或 cosine")
    if M < 2:
        raise ValueError("M 必须大于等于 2")
    if ef_construction < M:
        raise ValueError("ef_construction 必须大于等于 M")
    if ef_search < 1:
        raise ValueError("ef_search 必须大于等于 1")

    unique_dataset_ids = []
    for dataset_id in dataset_ids:
        if dataset_id not in unique_dataset_ids:
            unique_dataset_ids.append(dataset_id)
    if len(unique_dataset_ids) < 2:
        raise ValueError("联合索引至少需要选择两个数据集")

    datasets_by_id = {
        dataset.id: dataset
        for dataset in Dataset.query.filter(Dataset.id.in_(unique_dataset_ids)).all()
    }
    datasets = [datasets_by_id[dataset_id] for dataset_id in unique_dataset_ids if dataset_id in datasets_by_id]
    if len(datasets) != len(unique_dataset_ids):
        raise ValueError("部分数据集不存在")
    for dataset in datasets:
        if dataset.status not in ("processed", "indexed"):
            raise ValueError(f"数据集 {dataset.name} 尚未完成处理")

    joint_index = JointIndex(
        name=name.strip() or "联合索引",
        metric=metric,
        M=M,
        ef_construction=ef_construction,
        ef_search=ef_search,
        n_pcs=n_pcs,
        n_top_genes=n_top_genes,
        min_common_genes=min_common_genes,
        owner_id=owner_id,
        status="building",
    )
    db.session.add(joint_index)
    db.session.commit()

    try:
        _cb(progress_cb, 8, "正在分析数据集共同基因...")
        included, skipped, common_genes = _select_compatible_group(datasets, min_common_genes)
        included_ids = {dataset.id for dataset in included}

        for dataset in datasets:
            if dataset.id in included_ids:
                db.session.add(JointIndexDataset(
                    joint_index_id=joint_index.id,
                    dataset_id=dataset.id,
                    status="included",
                    n_cells=dataset.n_cells or 0,
                ))
            else:
                skip = next((item for item in skipped if item["dataset_id"] == dataset.id), None)
                db.session.add(JointIndexDataset(
                    joint_index_id=joint_index.id,
                    dataset_id=dataset.id,
                    status="skipped",
                    n_cells=0,
                    skip_reason=skip["reason"] if skip else "未进入最大兼容基因组",
                ))
        db.session.commit()

        if len(included) < 2:
            raise ValueError("兼容数据集不足两个，无法构建专业联合索引")
        if len(common_genes) < min_common_genes:
            raise ValueError(f"共同基因数不足：{len(common_genes)} < {min_common_genes}")

        _cb(progress_cb, 18, f"正在读取 {len(included)} 个兼容数据集的共同基因矩阵...")
        subsets = []
        dataset_id_chunks = []
        cell_index_chunks = []
        for dataset in included:
            subset = _load_dataset_subset(dataset, common_genes)
            subsets.append(subset)
            dataset_id_chunks.append(np.full(subset.n_obs, dataset.id, dtype=np.int64))
            cell_index_chunks.append(np.arange(subset.n_obs, dtype=np.int64))

        joint_adata = ad.concat(subsets, axis=0, join="inner", merge="same")
        dataset_id_map = np.concatenate(dataset_id_chunks)
        cell_index_map = np.concatenate(cell_index_chunks)

        _cb(progress_cb, 35, "正在归一化、筛选高变基因并计算 PCA...")
        sc.pp.normalize_total(joint_adata, target_sum=1e4)
        sc.pp.log1p(joint_adata)
        if 0 < n_top_genes < joint_adata.n_vars:
            sc.pp.highly_variable_genes(
                joint_adata,
                n_top_genes=min(n_top_genes, joint_adata.n_vars),
                flavor="seurat",
                batch_key="_dataset_id",
            )
            joint_adata = joint_adata[:, joint_adata.var["highly_variable"]].copy()

        sc.pp.scale(joint_adata, max_value=10, zero_center=False)
        effective_n_pcs = max(2, min(int(n_pcs), joint_adata.n_obs - 1, joint_adata.n_vars - 1))
        sc.tl.pca(joint_adata, n_comps=effective_n_pcs, svd_solver="arpack")

        _cb(progress_cb, 50, "正在执行 Harmony 批次校正...")
        sce.pp.harmony_integrate(
            joint_adata,
            key="_dataset_id",
            basis="X_pca",
            adjusted_basis="X_pca_harmony",
        )
        vectors = np.asarray(joint_adata.obsm["X_pca_harmony"], dtype=np.float32)

        _cb(progress_cb, 62, "正在计算联合 UMAP 坐标...")
        sc.pp.neighbors(
            joint_adata,
            use_rep="X_pca_harmony",
            n_neighbors=min(15, max(2, joint_adata.n_obs - 1)),
        )
        sc.tl.umap(joint_adata)
        umap = np.asarray(joint_adata.obsm["X_umap"], dtype=np.float32)

        _cb(progress_cb, 72, f"正在构建 {vectors.shape[0]} 个细胞的 HNSW 联合索引...")
        space = "cosine" if metric == "cosine" else "l2"
        index = hnswlib.Index(space=space, dim=vectors.shape[1])
        index.init_index(max_elements=vectors.shape[0], ef_construction=ef_construction, M=M)
        index.set_ef(ef_search)
        labels = np.arange(vectors.shape[0], dtype=np.int64)
        t0 = time.time()
        index.add_items(vectors, labels)
        build_time_ms = (time.time() - t0) * 1000

        _cb(progress_cb, 86, "正在保存联合索引文件...")
        index_filename = f"joint_{joint_index.id}_index_{metric}.bin"
        vector_filename = f"joint_{joint_index.id}_vectors.npy"
        umap_filename = f"joint_{joint_index.id}_umap.npy"
        mapping_filename = f"joint_{joint_index.id}_mapping.npz"

        index.save_index(str(_index_file(index_filename)))
        np.save(str(_cache_file(vector_filename)), vectors)
        np.save(str(_cache_file(umap_filename)), umap)
        np.savez(
            str(_cache_file(mapping_filename)),
            dataset_ids=dataset_id_map,
            cell_indices=cell_index_map,
        )

        joint_index.index_path = index_filename
        joint_index.vector_path = vector_filename
        joint_index.umap_path = umap_filename
        joint_index.mapping_path = mapping_filename
        joint_index.common_gene_count = len(common_genes)
        joint_index.n_cells = vectors.shape[0]
        joint_index.n_pcs = effective_n_pcs
        joint_index.build_time_ms = build_time_ms
        joint_index.status = "ready"
        joint_index.error_message = None
        db.session.commit()
        _cb(progress_cb, 100, "联合索引构建完成")
        return joint_index
    except Exception as exc:
        joint_index.status = "error"
        joint_index.error_message = str(exc)
        db.session.commit()
        raise


def search_joint_index(
    joint_index_id: int,
    query_dataset_id: int,
    query_cell_index: int,
    top_k: int = 20,
    user_id: int | None = None,
) -> dict:
    joint_index = db.session.get(JointIndex, joint_index_id)
    if not joint_index:
        raise ValueError("联合索引不存在")
    if joint_index.status != "ready":
        raise ValueError("联合索引尚未就绪")

    dataset_ids, cell_indices = _load_mapping(joint_index)
    matches = np.where((dataset_ids == query_dataset_id) & (cell_indices == query_cell_index))[0]
    if matches.size == 0:
        raise ValueError("查询细胞不在该联合索引的兼容数据集中")
    query_global_label = int(matches[0])

    vectors = _load_vectors(joint_index)
    top_k = max(1, min(int(top_k), min(100, vectors.shape[0] - 1)))
    index = _load_hnsw(joint_index, vectors.shape[1])
    fetch_k = min(top_k + 1, vectors.shape[0])

    t0 = time.time()
    labels, distances = index.knn_query(vectors[query_global_label:query_global_label + 1], k=fetch_k)
    query_time_ms = (time.time() - t0) * 1000

    pairs = []
    for label, distance in zip(labels[0].tolist(), distances[0].tolist()):
        if int(label) == query_global_label:
            continue
        pairs.append((int(label), float(distance)))
        if len(pairs) >= top_k:
            break

    result_labels = np.array([label for label, _ in pairs], dtype=np.int64)
    result_dataset_ids = dataset_ids[result_labels] if result_labels.size else np.array([], dtype=np.int64)
    result_cell_indices = cell_indices[result_labels] if result_labels.size else np.array([], dtype=np.int64)
    cells = _cell_info_map(result_dataset_ids, result_cell_indices)
    dataset_names = {
        dataset.id: dataset.name
        for dataset in Dataset.query.filter(Dataset.id.in_(set(result_dataset_ids.tolist()))).all()
    }

    results = []
    for rank, (global_label, distance) in enumerate(pairs, 1):
        dataset_id = int(dataset_ids[global_label])
        cell_index = int(cell_indices[global_label])
        cell = cells.get((dataset_id, cell_index))
        results.append({
            "rank": rank,
            "global_label": global_label,
            "dataset_id": dataset_id,
            "dataset_name": dataset_names.get(dataset_id, f"Dataset {dataset_id}"),
            "cell_id": cell.id if cell else None,
            "cell_index": cell_index,
            "cell_name": cell.cell_name if cell else "N/A",
            "distance": round(distance, 6),
            "cell_type": cell.cell_type if cell else "N/A",
            "disease": cell.disease if cell else "N/A",
            "age_group": cell.age_group if cell else "N/A",
        })

    log = JointQueryLog(
        joint_index_id=joint_index.id,
        user_id=user_id,
        query_dataset_id=query_dataset_id,
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
        "query_dataset_id": query_dataset_id,
        "query_cell_index": query_cell_index,
        "query_global_label": query_global_label,
        "joint_index_id": joint_index.id,
        "top_k": top_k,
        "searched_dataset_count": len({row.dataset_id for row in joint_index.datasets if row.status == "included"}),
        "metric": joint_index.metric,
    }


def joint_search_plot(
    joint_index_id: int,
    query_global_label: int,
    result_global_labels: list[int],
    max_background_points: int = 12_000,
) -> dict:
    joint_index = db.session.get(JointIndex, joint_index_id)
    if not joint_index or joint_index.status != "ready":
        raise ValueError("联合索引不存在或尚未就绪")

    coords = _load_umap(joint_index)
    dataset_ids, cell_indices = _load_mapping(joint_index)
    n_cells = coords.shape[0]
    if query_global_label < 0 or query_global_label >= n_cells:
        raise ValueError("查询 global_label 不在联合索引中")

    result_set = {int(label) for label in result_global_labels if 0 <= int(label) < n_cells}
    background_positions = [
        idx for idx in range(n_cells)
        if idx != query_global_label and idx not in result_set
    ]
    if len(background_positions) > max_background_points:
        rng = np.random.default_rng(seed=joint_index.id)
        background_positions = sorted(rng.choice(background_positions, size=max_background_points, replace=False).tolist())

    dataset_names = {
        dataset.id: dataset.name
        for dataset in Dataset.query.filter(Dataset.id.in_(set(dataset_ids.tolist()))).all()
    }
    background_labels = [dataset_names.get(int(dataset_ids[idx]), f"Dataset {int(dataset_ids[idx])}") for idx in background_positions]
    color_map = _build_color_map(background_labels, use_dark_cycle=True)
    muted_map = {label: _muted_color(color) for label, color in color_map.items()}
    fig = go.Figure()
    fig.add_trace(go.Scattergl(
        x=coords[background_positions, 0].astype(float).tolist(),
        y=coords[background_positions, 1].astype(float).tolist(),
        mode="markers",
        marker=dict(
            size=3,
            opacity=0.84,
            color=[muted_map[label] for label in background_labels],
            showscale=False,
        ),
        customdata=[
            [int(dataset_ids[idx]), dataset_names.get(int(dataset_ids[idx]), f"Dataset {int(dataset_ids[idx])}"), int(cell_indices[idx])]
            for idx in background_positions
        ],
        hovertemplate="数据集：%{customdata[1]}<br>细胞编号：%{customdata[2]:,}<extra></extra>",
        name="背景细胞",
        showlegend=False,
    ))

    highlight_labels = [label for label in result_global_labels if label in result_set and label != query_global_label]
    if highlight_labels:
        highlight_dataset_ids = dataset_ids[highlight_labels]
        highlight_cell_indices = cell_indices[highlight_labels]
        cells = _cell_info_map(highlight_dataset_ids, highlight_cell_indices)
        customdata = []
        for label in highlight_labels:
            dataset_id = int(dataset_ids[label])
            cell_index = int(cell_indices[label])
            cell = cells.get((dataset_id, cell_index))
            customdata.append([
                label,
                dataset_names.get(dataset_id, f"Dataset {dataset_id}"),
                cell_index,
                cell.cell_name if cell else "N/A",
                cell.cell_type if cell else "N/A",
            ])
        fig.add_trace(go.Scattergl(
            x=coords[highlight_labels, 0].astype(float).tolist(),
            y=coords[highlight_labels, 1].astype(float).tolist(),
            mode="markers",
            marker=dict(size=8, color="#0891b2", opacity=0.98, line=dict(width=1.4, color="#ffffff")),
            name="相似细胞",
            customdata=customdata,
            hovertemplate="数据集：%{customdata[1]}<br>细胞编号：%{customdata[2]:,}<br>细胞名称：%{customdata[3]}<br>细胞类型：%{customdata[4]}<extra></extra>",
            showlegend=False,
        ))

    query_dataset_id = int(dataset_ids[query_global_label])
    query_cell_index = int(cell_indices[query_global_label])
    query_cell = Cell.query.filter_by(dataset_id=query_dataset_id, cell_index=query_cell_index).first()
    fig.add_trace(go.Scattergl(
        x=[float(coords[query_global_label, 0])],
        y=[float(coords[query_global_label, 1])],
        mode="markers",
        marker=dict(size=16, color="#d97706", symbol="star", line=dict(width=2.4, color="#ffffff"), opacity=1.0),
        name="查询细胞",
        customdata=[[
            query_global_label,
            dataset_names.get(query_dataset_id, f"Dataset {query_dataset_id}"),
            query_cell_index,
            query_cell.cell_name if query_cell else "N/A",
            query_cell.cell_type if query_cell else "N/A",
        ]],
        hovertemplate="查询细胞<br>数据集：%{customdata[1]}<br>细胞编号：%{customdata[2]:,}<br>细胞名称：%{customdata[3]}<br>细胞类型：%{customdata[4]}<extra></extra>",
        showlegend=False,
    ))

    _apply_dark_layout(fig, title=f"{joint_index.name} · Harmony UMAP", xaxis_title="UMAP1", yaxis_title="UMAP2", height=640)
    plot_json = _fig_to_plotly_json(fig)
    plot_json["metadata"] = {
        "legend": {
            "target_trace_index": 0,
            "default_dimension": "dataset",
            "dimensions": {
                "dataset": _legend_dimension("数据集", 1, background_labels, muted_map),
            },
            "role_items": [
                {"label": "相似细胞", "color": "#0891b2"},
                {"label": "查询细胞", "color": "#d97706"},
            ],
        },
        "point_action": {"kind": "joint_cell", "customdata_index": 2},
    }
    return {"scatter_plot": plot_json}
