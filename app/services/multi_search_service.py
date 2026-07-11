"""多数据集 fan-out 检索服务。"""
import time
from app.extensions import db
from app.models import AnnIndex, Cell, Dataset
from app.services.ann_service import query_ann_index
from app.services.data_service import load_vectors


def search_across_datasets(
    source_dataset_id: int,
    source_index_id: int,
    query_cell_index: int,
    top_k: int = 20,
    target_dataset_ids: list[int] = None,
    user_id: int | None = None,
) -> dict:
    """使用多个 ready 索引执行 fan-out 检索并合并排序。"""
    source_dataset = db.session.get(Dataset, source_dataset_id)
    source_index = db.session.get(AnnIndex, source_index_id)
    if not source_dataset or not source_index:
        raise ValueError("源数据集或源索引不存在")
    if source_index.dataset_id != source_dataset_id:
        raise ValueError("源索引不属于源数据集")
    if source_index.status != "ready":
        raise ValueError("源索引尚未就绪")
    if source_index.lifecycle != "active":
        raise ValueError("源索引不是当前保留索引")

    source_vectors = load_vectors(source_dataset)
    if query_cell_index < 0 or query_cell_index >= source_vectors.shape[0]:
        raise ValueError(f"query_cell_index 必须在 [0, {source_vectors.shape[0] - 1}] 范围内")

    query_vector = source_vectors[query_cell_index : query_cell_index + 1]
    top_k = max(1, min(int(top_k), 100))
    candidate_k = max(top_k, 20)

    index_query = (
        AnnIndex.query
        .join(Dataset, Dataset.id == AnnIndex.dataset_id)
        .filter(
            AnnIndex.status == "ready",
            AnnIndex.lifecycle == "active",
            AnnIndex.metric == source_index.metric,
            Dataset.status.in_(["processed", "indexed"]),
        )
        .order_by(AnnIndex.dataset_id.asc(), AnnIndex.id.asc())
    )
    if target_dataset_ids:
        index_query = index_query.filter(AnnIndex.dataset_id.in_(target_dataset_ids))

    indexes = index_query.all()
    # 同一数据集多套索引时，只使用第一套同 metric 的 ready 索引，避免重复结果。
    selected_indexes = {}
    for idx in indexes:
        selected_indexes.setdefault(idx.dataset_id, idx)

    merged = []
    skipped = []
    t0 = time.time()

    for idx in selected_indexes.values():
        dataset = idx.dataset
        try:
            vectors = load_vectors(dataset)
            if vectors.shape[1] != query_vector.shape[1]:
                skipped.append({
                    "dataset_id": dataset.id,
                    "dataset_name": dataset.name,
                    "reason": "向量维度不一致",
                })
                continue
            fetch_k = min(candidate_k + (1 if dataset.id == source_dataset_id else 0), vectors.shape[0])
            if fetch_k <= 0:
                continue
            labels, distances = query_ann_index(idx, vectors, query_vector, fetch_k)
        except Exception as exc:
            skipped.append({
                "dataset_id": dataset.id,
                "dataset_name": dataset.name,
                "reason": str(exc),
            })
            continue

        pairs = []
        for cell_idx, dist in zip(labels[0].tolist(), distances[0].tolist()):
            if dataset.id == source_dataset_id and int(cell_idx) == query_cell_index:
                continue
            pairs.append((int(cell_idx), float(dist)))
            if len(pairs) >= candidate_k:
                break

        if not pairs:
            continue

        cell_indices = [cell_idx for cell_idx, _ in pairs]
        cells = {
            cell.cell_index: cell
            for cell in Cell.query.filter(
                Cell.dataset_id == dataset.id,
                Cell.cell_index.in_(cell_indices),
            ).all()
        }

        for cell_idx, dist in pairs:
            cell = cells.get(cell_idx)
            merged.append({
                "dataset_id": dataset.id,
                "dataset_name": dataset.name,
                "index_id": idx.id,
                "metric": idx.metric,
                "cell_id": cell.id if cell else None,
                "cell_index": cell_idx,
                "cell_name": cell.cell_name if cell else "N/A",
                "distance": round(dist, 6),
                "cell_type": cell.cell_type if cell else "N/A",
                "disease": cell.disease if cell else "N/A",
                "age_group": cell.age_group if cell else "N/A",
            })

    merged.sort(key=lambda item: item["distance"])
    results = []
    for rank, row in enumerate(merged[:top_k], 1):
        row = dict(row)
        row["rank"] = rank
        results.append(row)

    query_time_ms = (time.time() - t0) * 1000
    return {
        "results": results,
        "query_time_ms": round(query_time_ms, 3),
        "query_cell_index": query_cell_index,
        "top_k": top_k,
        "source_dataset_id": source_dataset_id,
        "source_index_id": source_index_id,
        "metric": source_index.metric,
        "searched_dataset_count": len(selected_indexes) - len(skipped),
        "skipped": skipped,
    }
