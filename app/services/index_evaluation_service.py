"""Async persistent ANN index evaluation service."""
from __future__ import annotations

from app.extensions import db
from app.models import AnnIndex, Dataset, IndexEvaluation
from app.services.eval_service import evaluate_index_metrics
from app.services.recommendation_service import (
    assign_recommendation_tags,
    quality_gate,
    quality_label,
    tags_to_string,
)


def index_evaluation_to_dict(evaluation: IndexEvaluation) -> dict:
    dataset_name = evaluation.dataset.name if evaluation.dataset else None
    index_label = None
    if evaluation.ann_index:
        index_label = f"#{evaluation.ann_index.id} {evaluation.ann_index.algorithm} {evaluation.ann_index.metric}"
    return {
        "id": evaluation.id,
        "dataset_id": evaluation.dataset_id,
        "dataset_name": dataset_name,
        "index_id": evaluation.index_id,
        "index_label": index_label,
        "algorithm": evaluation.algorithm,
        "metric": evaluation.metric,
        "sample_size": evaluation.sample_size,
        "top_k": evaluation.top_k,
        "seed": evaluation.seed,
        "recall_at_k": evaluation.recall_at_k,
        "avg_query_time_ms": evaluation.avg_query_time_ms,
        "p95_query_time_ms": evaluation.p95_query_time_ms,
        "avg_exact_time_ms": evaluation.avg_exact_time_ms,
        "speedup": evaluation.speedup,
        "index_size_bytes": evaluation.index_size_bytes,
        "quality": evaluation.quality,
        "quality_gate": quality_gate(evaluation.recall_at_k),
        "recommendation": evaluation.recommendation,
        "status": evaluation.status,
        "error_message": evaluation.error_message,
        "created_at": evaluation.created_at.isoformat() if evaluation.created_at else None,
    }


def refresh_evaluation_recommendations(dataset_id: int, sample_size: int, top_k: int, seed: int):
    """Recompute comparative tags for latest successful evaluation per index."""
    rows = (
        IndexEvaluation.query
        .filter_by(dataset_id=dataset_id, sample_size=sample_size, top_k=top_k, seed=seed, status="success")
        .order_by(IndexEvaluation.created_at.desc())
        .all()
    )
    latest_by_index: dict[int, IndexEvaluation] = {}
    for row in rows:
        latest_by_index.setdefault(row.index_id, row)

    latest_rows = list(latest_by_index.values())
    labels = assign_recommendation_tags(latest_rows)
    for row in latest_rows:
        row.quality = quality_label(row.recall_at_k)
        row.recommendation = tags_to_string(labels.get(row.id))
    db.session.commit()


def run_index_evaluation(
    dataset_id: int,
    index_id: int,
    sample_size: int = 100,
    top_k: int = 10,
    seed: int = 42,
    progress_cb=None,
) -> IndexEvaluation:
    """Evaluate one ready persisted ANN index and store the result."""

    def _cb(progress: int, message: str):
        if progress_cb:
            progress_cb(progress, message)

    dataset = db.session.get(Dataset, dataset_id)
    ann_index = db.session.get(AnnIndex, index_id)
    if not dataset:
        raise ValueError("Dataset does not exist")
    if not ann_index or ann_index.dataset_id != dataset_id:
        raise ValueError("Index does not belong to the selected dataset")
    if ann_index.status != "ready":
        raise ValueError("Index is not ready")

    sample_size = max(1, min(int(sample_size), 200))
    top_k = max(1, min(int(top_k), 100))
    seed = int(seed)

    evaluation = IndexEvaluation(
        dataset_id=dataset_id,
        index_id=index_id,
        metric=ann_index.metric,
        algorithm=ann_index.algorithm or "hnswlib_hnsw",
        sample_size=sample_size,
        top_k=top_k,
        seed=seed,
        index_size_bytes=ann_index.index_size_bytes,
        status="running",
    )
    db.session.add(evaluation)
    db.session.commit()

    try:
        _cb(10, "加载向量数据和真实索引...")
        metrics = evaluate_index_metrics(
            dataset_id=dataset_id,
            index_id=index_id,
            sample_size=sample_size,
            top_k=top_k,
            seed=seed,
            max_sample_size=200,
        )
        _cb(90, "保存评估指标...")
        evaluation.metric = metrics["metric"]
        evaluation.algorithm = metrics["algorithm"]
        evaluation.sample_size = metrics["sample_size"]
        evaluation.top_k = metrics["top_k"]
        evaluation.seed = metrics["seed"]
        evaluation.recall_at_k = metrics["recall_at_k"]
        evaluation.avg_query_time_ms = metrics["avg_query_time_ms"]
        evaluation.p95_query_time_ms = metrics["p95_query_time_ms"]
        evaluation.avg_exact_time_ms = metrics["avg_exact_time_ms"]
        evaluation.speedup = metrics["speedup"]
        evaluation.index_size_bytes = metrics["index_size_bytes"]
        evaluation.quality = metrics["quality"]
        evaluation.status = "success"
        evaluation.error_message = None
        db.session.commit()
        refresh_evaluation_recommendations(dataset_id, evaluation.sample_size, evaluation.top_k, evaluation.seed)
        _cb(100, "真实索引评估完成。")
        return evaluation
    except Exception as exc:
        evaluation.status = "error"
        evaluation.error_message = str(exc)
        db.session.commit()
        raise
