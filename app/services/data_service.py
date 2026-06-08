import json
import numpy as np
import scanpy as sc
from flask import current_app
from app.extensions import db
from app.models import Dataset, Cell


def process_h5ad_dataset(dataset_id: int, progress_cb=None) -> Dataset:
    """读取 h5ad 文件，提取 PCA 向量缓存为 npy，将细胞元信息保存到 SQLite。

    Args:
        dataset_id: 数据集 ID
        progress_cb: 可选的进度回调 progress_cb(progress: int, message: str)
    """
    def _cb(p, msg):
        if progress_cb:
            progress_cb(p, msg)

    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        raise ValueError(f"数据集 {dataset_id} 不存在")

    _cb(5, "正在读取 h5ad 文件...")
    try:
        adata = sc.read_h5ad(dataset.file_path)
    except Exception as e:
        dataset.status = "error"
        dataset.error_message = f"读取 h5ad 文件失败: {str(e)}"
        db.session.commit()
        raise

    _cb(20, "文件读取完成，正在检查 PCA 向量...")
    # 检查是否存在 X_pca
    if "X_pca" not in adata.obsm:
        dataset.status = "error"
        dataset.error_message = "adata.obsm 中未找到 X_pca，请确保已执行 PCA 降维。"
        db.session.commit()
        raise ValueError(dataset.error_message)

    _cb(35, "正在提取 PCA 向量并保存缓存...")
    # 提取向量并缓存为 npy
    vectors = np.array(adata.obsm["X_pca"], dtype=np.float32)
    vector_path = f"dataset_{dataset_id}_vectors.npy"
    full_vector_path = str(
        (
            __import__("pathlib").Path(current_app.config["CACHE_DIR"]) / vector_path
        ).resolve()
    )
    np.save(full_vector_path, vectors)

    # 更新数据集元信息
    dataset.n_cells = adata.n_obs
    dataset.n_genes = adata.n_vars
    dataset.vector_dim = vectors.shape[1]
    dataset.vector_path = vector_path

    _cb(50, "向量缓存完成，正在清理旧细胞记录...")
    # 删除该数据集已有的细胞记录（支持重复处理）
    Cell.query.filter_by(dataset_id=dataset_id).delete()

    _cb(60, "正在提取细胞元信息，批量写入数据库...")
    # 提取 obs 中的元信息字段
    known_cols = {"cell_type", "disease", "AgeGroup"}
    obs = adata.obs
    extra_cols = [c for c in obs.columns if c not in known_cols]

    # 批量插入细胞元信息
    cell_records = []
    for i in range(adata.n_obs):
        row = obs.iloc[i]
        extra = {c: str(row[c]) for c in extra_cols}

        cell_records.append(
            Cell(
                dataset_id=dataset_id,
                cell_index=i,
                cell_name=str(obs.index[i]),
                cell_type=str(row.get("cell_type", "")) if "cell_type" in obs.columns else None,
                disease=str(row.get("disease", "")) if "disease" in obs.columns else None,
                age_group=str(row.get("AgeGroup", "")) if "AgeGroup" in obs.columns else None,
                metadata_json=json.dumps(extra, ensure_ascii=False),
            )
        )

    _cb(80, f"正在提交 {len(cell_records)} 条细胞记录...")
    db.session.bulk_save_objects(cell_records)
    dataset.status = "processed"
    dataset.error_message = None
    db.session.commit()

    _cb(100, "数据集处理完成。")
    return dataset


def load_vectors(dataset: Dataset) -> np.ndarray:
    """从 npy 缓存文件加载向量矩阵。"""
    import pathlib

    full_path = pathlib.Path(current_app.config["CACHE_DIR"]) / dataset.vector_path
    if not full_path.exists():
        raise FileNotFoundError(f"向量缓存文件不存在: {full_path}")
    return np.load(str(full_path))
