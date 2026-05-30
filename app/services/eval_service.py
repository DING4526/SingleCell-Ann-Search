import time
import random
import numpy as np
from app.extensions import db
from app.models import Dataset, AnnIndex
from app.services.data_service import load_vectors
from app.services.ann_service import load_hnsw_index


def exact_search(vectors: np.ndarray, query_vector: np.ndarray, top_k: int, metric: str = "l2") -> tuple:
    """暴力精确最近邻检索。

    返回 (indices, distances)，按距离升序排列。
    """
    query = query_vector.reshape(1, -1)
    if metric == "cosine":
        # 余弦距离 = 1 - 余弦相似度
        norms_q = np.linalg.norm(query, axis=1, keepdims=True)
        norms_v = np.linalg.norm(vectors, axis=1, keepdims=True)
        similarities = (query @ vectors.T) / (norms_q * norms_v.T + 1e-10)
        distances = 1.0 - similarities[0]
    else:
        # L2 平方距离
        diff = vectors - query
        distances = np.sum(diff ** 2, axis=1)

    indices = np.argsort(distances)[:top_k]
    return indices.tolist(), distances[indices].tolist()


def evaluate_index(
    dataset_id: int,
    index_id: int,
    sample_size: int = 10,
    top_k: int = 10,
) -> dict:
    """评估 ANN 索引性能：与精确检索对比。

    返回 avg_recall_at_k、avg_ann_time_ms、avg_exact_time_ms、speedup。
    """
    sample_size = min(sample_size, 50)

    dataset = db.session.get(Dataset, dataset_id)
    ann_index_record = db.session.get(AnnIndex, index_id)

    if not dataset or not ann_index_record:
        raise ValueError("数据集或索引不存在")

    vectors = load_vectors(dataset)
    n_cells = vectors.shape[0]

    hnsw_index = load_hnsw_index(ann_index_record, vectors.shape[1])

    # 随机采样细胞
    sample_indices = random.sample(range(n_cells), min(sample_size, n_cells))

    recalls = []
    ann_times = []
    exact_times = []

    for cell_idx in sample_indices:
        query_vector = vectors[cell_idx : cell_idx + 1]

        # ANN 近似检索
        t0 = time.time()
        ann_labels, _ = hnsw_index.knn_query(query_vector, k=top_k + 1)
        ann_time_ms = (time.time() - t0) * 1000
        ann_labels = [l for l in ann_labels[0].tolist() if l != cell_idx][:top_k]

        # 精确暴力检索
        t0 = time.time()
        exact_labels, _ = exact_search(vectors, query_vector, top_k + 1, ann_index_record.metric)
        exact_time_ms = (time.time() - t0) * 1000
        exact_labels = [l for l in exact_labels if l != cell_idx][:top_k]

        # 计算召回率
        if exact_labels:
            recall = len(set(ann_labels) & set(exact_labels)) / len(exact_labels)
        else:
            recall = 1.0

        recalls.append(recall)
        ann_times.append(ann_time_ms)
        exact_times.append(exact_time_ms)

    avg_recall = float(np.mean(recalls))
    avg_ann = float(np.mean(ann_times))
    avg_exact = float(np.mean(exact_times))
    speedup = avg_exact / avg_ann if avg_ann > 0 else float("inf")

    return {
        "avg_recall_at_k": round(avg_recall, 4),
        "avg_ann_time_ms": round(avg_ann, 4),
        "avg_exact_time_ms": round(avg_exact, 4),
        "speedup": round(speedup, 2),
        "sample_size": len(sample_indices),
        "top_k": top_k,
    }
