from __future__ import annotations

import time

import numpy as np

from app.extensions import db
from app.models import AnnIndex, Dataset
from app.services.ann_backend_service import normalize_algorithm
from app.services.ann_service import load_ann_backend
from app.services.data_service import load_vectors
from app.services.recommendation_service import quality_gate, quality_label


def exact_search(vectors: np.ndarray, query_vector: np.ndarray, top_k: int, metric: str = "l2") -> tuple:
    """Brute-force exact nearest-neighbor search."""
    query = query_vector.reshape(1, -1)
    if metric == "cosine":
        norms_q = np.linalg.norm(query, axis=1, keepdims=True)
        norms_v = np.linalg.norm(vectors, axis=1, keepdims=True)
        similarities = (query @ vectors.T) / (norms_q * norms_v.T + 1e-10)
        distances = 1.0 - similarities[0]
    else:
        diff = vectors - query
        distances = np.sum(diff ** 2, axis=1)

    indices = np.argsort(distances)[:top_k]
    return indices.tolist(), distances[indices].tolist()


def _round(value: float | None, digits: int = 4):
    if value is None:
        return None
    return round(float(value), digits)


def evaluate_index_metrics(
    dataset_id: int,
    index_id: int,
    sample_size: int = 100,
    top_k: int = 10,
    seed: int = 42,
    max_sample_size: int = 200,
) -> dict:
    """Evaluate one persisted ANN index against exact search with deterministic sampling."""
    dataset = db.session.get(Dataset, dataset_id)
    ann_index_record = db.session.get(AnnIndex, index_id)

    if not dataset or not ann_index_record:
        raise ValueError("Dataset or index does not exist")
    if ann_index_record.dataset_id != dataset_id:
        raise ValueError("Index does not belong to the selected dataset")
    if ann_index_record.status != "ready":
        raise ValueError("Index is not ready")

    vectors = load_vectors(dataset)
    n_cells = vectors.shape[0]
    if n_cells < 2:
        raise ValueError("Dataset needs at least two cells for index evaluation")

    top_k = max(1, min(int(top_k), n_cells - 1))
    sample_size = max(1, min(int(sample_size), min(int(max_sample_size), n_cells)))
    rng = np.random.default_rng(int(seed))
    sample_indices = rng.choice(np.arange(n_cells), size=sample_size, replace=False).tolist()

    loaded = load_ann_backend(ann_index_record, vectors.shape[1])
    recalls: list[float] = []
    ann_times: list[float] = []
    exact_times: list[float] = []
    fetch_k = min(top_k + 1, n_cells)

    for cell_idx in sample_indices:
        query_vector = vectors[cell_idx : cell_idx + 1]

        t0 = time.perf_counter()
        ann_labels, _ = loaded.query(query_vector, fetch_k)
        ann_times.append((time.perf_counter() - t0) * 1000)
        ann_neighbors = [
            int(label)
            for label in ann_labels[0].tolist()
            if int(label) >= 0 and int(label) != cell_idx
        ][:top_k]

        t0 = time.perf_counter()
        exact_labels, _ = exact_search(vectors, query_vector, fetch_k, ann_index_record.metric)
        exact_times.append((time.perf_counter() - t0) * 1000)
        exact_neighbors = [int(label) for label in exact_labels if int(label) != cell_idx][:top_k]

        recall = len(set(ann_neighbors) & set(exact_neighbors)) / len(exact_neighbors) if exact_neighbors else 1.0
        recalls.append(recall)

    avg_recall = float(np.mean(recalls)) if recalls else 0.0
    avg_ann = float(np.mean(ann_times)) if ann_times else 0.0
    p95_ann = float(np.percentile(ann_times, 95)) if ann_times else 0.0
    avg_exact = float(np.mean(exact_times)) if exact_times else 0.0
    speedup = avg_exact / avg_ann if avg_ann > 0 else 0.0
    quality = quality_label(avg_recall)

    return {
        "dataset_id": dataset_id,
        "index_id": index_id,
        "algorithm": normalize_algorithm(ann_index_record.algorithm),
        "metric": ann_index_record.metric,
        "recall_at_k": _round(avg_recall),
        "avg_recall_at_k": _round(avg_recall),
        "avg_query_time_ms": _round(avg_ann),
        "avg_ann_time_ms": _round(avg_ann),
        "p95_query_time_ms": _round(p95_ann),
        "avg_exact_time_ms": _round(avg_exact),
        "speedup": _round(speedup, 3),
        "sample_size": len(sample_indices),
        "top_k": top_k,
        "seed": int(seed),
        "index_size_bytes": ann_index_record.index_size_bytes,
        "quality": quality,
        "quality_gate": quality_gate(avg_recall),
    }


def evaluate_index(
    dataset_id: int,
    index_id: int,
    sample_size: int = 10,
    top_k: int = 10,
) -> dict:
    """Backward-compatible synchronous evaluation used by the Evaluation page."""
    return evaluate_index_metrics(
        dataset_id=dataset_id,
        index_id=index_id,
        sample_size=sample_size,
        top_k=top_k,
        seed=42,
        max_sample_size=50,
    )
