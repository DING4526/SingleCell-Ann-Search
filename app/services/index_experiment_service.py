"""Persistent multi-index experiment, evaluation, selection, and cleanup workflow."""
from __future__ import annotations

import json
import pathlib
import tempfile
import time
from datetime import datetime
from typing import Any

import numpy as np
from flask import current_app

from app.extensions import db
from app.models import AnnIndex, Dataset, IndexExperiment, IndexExperimentRun
from app.services.ann_backend_service import (
    FAISS_FLAT,
    FAISS_IVF_FLAT,
    FAISS_IVF_PQ,
    HNSWLIB_HNSW,
    HNSWLIB_RP_HNSW,
    algorithm_catalog,
    build_backend_index,
    load_backend_index,
    merge_params,
)
from app.services.ann_service import build_ann_index, load_ann_backend
from app.services.data_service import load_vectors
from app.services.recommendation_service import (
    NOT_RECOMMENDED_RECALL,
    assign_selection_recommendations,
    quality_label,
    tags_to_string,
)


WORKFLOW_VERSION = 2
ACTIVE_EXPERIMENT_STATUSES = ("pending", "running", "ready_for_selection")

DEFAULT_CANDIDATES = [
    {"key": "hnsw_fast", "name": "HNSW fast", "algorithm": HNSWLIB_HNSW, "params": {"M": 8, "ef_construction": 80, "ef_search": 32}},
    {"key": "hnsw_balanced", "name": "HNSW balanced", "algorithm": HNSWLIB_HNSW, "params": {"M": 16, "ef_construction": 200, "ef_search": 100}},
    {"key": "hnsw_high_recall", "name": "HNSW high recall", "algorithm": HNSWLIB_HNSW, "params": {"M": 32, "ef_construction": 300, "ef_search": 220}},
    {"key": "rp_hnsw", "name": "RP-HNSW", "algorithm": HNSWLIB_RP_HNSW, "params": {"projection_dim": 16, "random_state": 42, "M": 12, "ef_construction": 120, "ef_search": 64}},
    {"key": "faiss_ivf_flat", "name": "FAISS IVF-Flat", "algorithm": FAISS_IVF_FLAT, "params": {}},
    {"key": "faiss_ivf_pq_compact", "name": "FAISS IVF-PQ compact", "algorithm": FAISS_IVF_PQ, "params": {"nbits": 4}},
]


class ExperimentConflict(RuntimeError):
    """Raised when an experiment lifecycle transition conflicts with current state."""


def _json_object(value: str | None) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _json_list(value: str | None) -> list:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def _round(value: float | None, digits: int = 4):
    return None if value is None else round(float(value), digits)


def experiment_candidates(keys: list[str] | None = None) -> list[dict]:
    selected = set(keys or [])
    if not selected:
        return [dict(item, params=dict(item.get("params") or {})) for item in DEFAULT_CANDIDATES]
    return [dict(item, params=dict(item.get("params") or {})) for item in DEFAULT_CANDIDATES if item["key"] in selected]


def validate_candidate_configs(dataset: Dataset, configs: list[dict] | None = None, keys: list[str] | None = None) -> list[dict]:
    raw_configs = configs if configs is not None else experiment_candidates(keys)
    if not 2 <= len(raw_configs) <= 12:
        raise ValueError("候选配置数量必须在 2 到 12 之间")

    catalog = {item["key"]: item for item in algorithm_catalog(dataset.n_cells, dataset.vector_dim)}
    normalized: list[dict] = []
    fingerprints: set[str] = set()
    keys_seen: set[str] = set()
    for position, raw in enumerate(raw_configs, 1):
        if not isinstance(raw, dict):
            raise ValueError("candidate_configs 必须是对象数组")
        algorithm = str(raw.get("algorithm") or "").strip()
        if algorithm == FAISS_FLAT:
            raise ValueError("FAISS Flat 是固定精确基线，不能作为候选索引")
        catalog_row = catalog.get(algorithm)
        if not catalog_row:
            raise ValueError(f"不支持的候选算法：{algorithm}")
        if not catalog_row.get("available"):
            raise ValueError(catalog_row.get("disabled_reason") or f"算法 {algorithm} 当前不可用")

        params = raw.get("params") or {}
        if not isinstance(params, dict):
            raise ValueError("候选 params 必须是对象")
        params = merge_params(algorithm, params, n_cells=dataset.n_cells, dim=dataset.vector_dim)
        fingerprint = json.dumps({"algorithm": algorithm, "params": params}, sort_keys=True, ensure_ascii=False)
        if fingerprint in fingerprints:
            raise ValueError("候选中存在算法与参数完全相同的重复配置")
        fingerprints.add(fingerprint)

        key = str(raw.get("key") or f"candidate_{position}").strip()[:80]
        if not key or key in keys_seen:
            raise ValueError("候选 key 不能为空且必须唯一")
        keys_seen.add(key)
        name = str(raw.get("name") or catalog_row["label"]).strip()[:120]
        if not name:
            raise ValueError("候选名称不能为空")
        normalized.append({"key": key, "name": name, "algorithm": algorithm, "params": params})
    return normalized


def _index_for_run(run_id: int) -> AnnIndex | None:
    return AnnIndex.query.filter_by(source_run_id=run_id).order_by(AnnIndex.id.desc()).first()


def _index_payload(index: AnnIndex | None) -> dict | None:
    if not index:
        return None
    return {
        "id": index.id,
        "algorithm": index.algorithm,
        "metric": index.metric,
        "lifecycle": index.lifecycle or "active",
        "selection_labels": [item for item in (index.selection_labels or "").split(",") if item],
        "status": index.status,
        "index_size_bytes": index.index_size_bytes,
        "build_time_ms": index.build_time_ms,
        "error_message": index.error_message,
    }


def run_to_dict(run: IndexExperimentRun) -> dict:
    return {
        "id": run.id,
        "name": run.name,
        "algorithm": run.algorithm,
        "params": _json_object(run.params_json),
        "status": run.status,
        "skip_reason": run.skip_reason,
        "error_message": run.error_message,
        "recall_at_k": run.recall_at_k,
        "avg_query_time_ms": run.avg_query_time_ms,
        "p95_query_time_ms": run.p95_query_time_ms,
        "avg_exact_time_ms": run.avg_exact_time_ms,
        "speedup": run.speedup,
        "build_time_ms": run.build_time_ms,
        "index_size_bytes": run.index_size_bytes,
        "memory_bytes": run.memory_bytes,
        "query_count": run.query_count,
        "quality": run.quality,
        "recommendation": run.recommendation,
        "index": _index_payload(_index_for_run(run.id)),
    }


def _workflow_config(experiment: IndexExperiment) -> dict:
    return _json_object(experiment.config_json)


def experiment_to_dict(experiment: IndexExperiment, include_runs: bool = True) -> dict:
    config = _workflow_config(experiment)
    selected_run_ids = [int(value) for value in _json_list(experiment.selected_run_ids_json)]
    runs = [run_to_dict(run) for run in experiment.runs] if include_runs else []
    eligible_count = sum(
        1 for run in experiment.runs
        if run.status == "success" and float(run.recall_at_k or 0.0) >= NOT_RECOMMENDED_RECALL
    )
    payload = {
        "id": experiment.id,
        "dataset_id": experiment.dataset_id,
        "dataset_name": experiment.dataset.name if experiment.dataset else None,
        "created_by_id": experiment.created_by_id,
        "created_by_name": experiment.created_by.username if experiment.created_by else None,
        "metric": experiment.metric,
        "sample_size": experiment.sample_size,
        "top_k": experiment.top_k,
        "seed": experiment.seed or 42,
        "repetitions": experiment.repetitions or 3,
        "warmup_count": experiment.warmup_count or 10,
        "candidate_count": experiment.candidate_count,
        "config": config,
        "workflow_version": int(config.get("workflow_version") or 1),
        "status": experiment.status,
        "best_recall_run_id": experiment.best_recall_run_id,
        "best_speed_run_id": experiment.best_speed_run_id,
        "best_balanced_run_id": experiment.best_balanced_run_id,
        "recommended_run_ids": list(dict.fromkeys([
            value for value in [
                experiment.best_recall_run_id,
                experiment.best_speed_run_id,
                experiment.best_balanced_run_id,
            ] if value is not None
        ])),
        "exact_baseline": {
            "algorithm": FAISS_FLAT,
            "avg_query_time_ms": experiment.exact_avg_query_time_ms,
            "p95_query_time_ms": experiment.exact_p95_query_time_ms,
        },
        "selected_run_ids": selected_run_ids,
        "finalized_at": experiment.finalized_at.isoformat() if experiment.finalized_at else None,
        "reclaimed_bytes": int(experiment.reclaimed_bytes or 0),
        "finalizable": (
            int(config.get("workflow_version") or 1) >= WORKFLOW_VERSION
            and experiment.status == "ready_for_selection"
            and eligible_count >= 2
        ),
        "error_message": experiment.error_message,
        "created_at": experiment.created_at.isoformat() if experiment.created_at else None,
    }
    if include_runs:
        payload["runs"] = runs
    result = _json_object(experiment.result_json)
    if result.get("finalization"):
        payload["finalization"] = result["finalization"]
    return payload


def create_index_experiment(
    dataset_id: int,
    metric: str = "l2",
    sample_size: int = 100,
    top_k: int = 10,
    seed: int = 42,
    repetitions: int = 3,
    warmup_count: int = 10,
    candidate_configs: list[dict] | None = None,
    candidate_keys: list[str] | None = None,
) -> IndexExperiment:
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset or dataset.status not in ("processed", "indexed"):
        raise ValueError("数据集需要先完成处理")
    if metric not in ("l2", "cosine"):
        raise ValueError("metric 仅支持 l2 或 cosine")

    existing = IndexExperiment.query.filter(
        IndexExperiment.dataset_id == dataset_id,
        IndexExperiment.status.in_(ACTIVE_EXPERIMENT_STATUSES),
    ).order_by(IndexExperiment.id.desc()).first()
    if existing:
        raise ExperimentConflict(f"数据集已有待处理实验 #{existing.id}，请先完成选优或放弃该实验")

    candidates = validate_candidate_configs(dataset, candidate_configs, candidate_keys)
    sample_size = max(1, min(int(sample_size), min(200, int(dataset.n_cells or sample_size))))
    top_k = max(1, min(int(top_k), min(100, max(1, int(dataset.n_cells or 2) - 1))))
    repetitions = max(1, min(int(repetitions), 10))
    warmup_count = max(0, min(int(warmup_count), sample_size))
    experiment = IndexExperiment(
        dataset_id=dataset_id,
        metric=metric,
        sample_size=sample_size,
        top_k=top_k,
        seed=int(seed),
        repetitions=repetitions,
        warmup_count=warmup_count,
        candidate_count=len(candidates),
        config_json=json.dumps({
            "workflow_version": WORKFLOW_VERSION,
            "exact_backend": FAISS_FLAT,
            "candidates": candidates,
        }, ensure_ascii=False),
        status="pending",
    )
    db.session.add(experiment)
    db.session.flush()
    for candidate in candidates:
        db.session.add(IndexExperimentRun(
            experiment_id=experiment.id,
            name=candidate["name"],
            algorithm=candidate["algorithm"],
            params_json=json.dumps(candidate["params"], ensure_ascii=False),
            status="pending",
        ))
    db.session.commit()
    return experiment


def _neighbors(labels: np.ndarray, query_index: int, top_k: int) -> list[int]:
    return [
        int(label) for label in labels.tolist()
        if int(label) >= 0 and int(label) != query_index
    ][:top_k]


def _benchmark_loaded_index(
    loaded: Any,
    vectors: np.ndarray,
    sample_indices: list[int],
    top_k: int,
    repetitions: int,
    warmup_count: int,
    exact_neighbors: dict[int, list[int]] | None = None,
) -> dict:
    fetch_k = min(top_k + 1, vectors.shape[0])
    for cell_idx in sample_indices[:warmup_count]:
        loaded.query(vectors[cell_idx:cell_idx + 1], fetch_k)

    query_times: list[float] = []
    observed: dict[int, list[int]] = {}
    for repetition in range(repetitions):
        for cell_idx in sample_indices:
            t0 = time.perf_counter()
            labels, _ = loaded.query(vectors[cell_idx:cell_idx + 1], fetch_k)
            query_times.append((time.perf_counter() - t0) * 1000)
            if repetition == 0:
                observed[cell_idx] = _neighbors(labels[0], cell_idx, top_k)

    recalls: list[float] = []
    if exact_neighbors is not None:
        for cell_idx in sample_indices:
            expected = exact_neighbors[cell_idx]
            actual = observed[cell_idx]
            recalls.append(len(set(actual) & set(expected)) / len(expected) if expected else 1.0)
    return {
        "neighbors": observed,
        "recall_at_k": float(np.mean(recalls)) if recalls else 1.0,
        "avg_query_time_ms": float(np.mean(query_times)) if query_times else 0.0,
        "p95_query_time_ms": float(np.percentile(query_times, 95)) if query_times else 0.0,
        "query_count": len(query_times),
    }


def _safe_artifact_path(filename: str) -> pathlib.Path:
    root = pathlib.Path(current_app.config["INDEX_DIR"]).resolve()
    candidate = (root / filename).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("索引文件路径越界")
    return candidate


def _discard_index_artifact(index: AnnIndex) -> tuple[int, list[str]]:
    removed_bytes = 0
    errors: list[str] = []
    index.lifecycle = "discarded"
    index.discarded_at = index.discarded_at or datetime.utcnow()
    for filename in [index.index_path, index.preprocess_path]:
        if not filename:
            continue
        try:
            path = _safe_artifact_path(filename)
            if path.exists():
                removed_bytes += path.stat().st_size
                path.unlink()
        except Exception as exc:
            errors.append(str(exc))
    index.status = "cleanup_error" if errors else "deleted"
    index.error_message = "; ".join(errors) if errors else None
    return removed_bytes, errors


def _update_selection_recommendations(experiment: IndexExperiment, successful: list[IndexExperimentRun]) -> list[int]:
    labels, selected = assign_selection_recommendations(successful)
    experiment.best_recall_run_id = None
    experiment.best_speed_run_id = None
    experiment.best_balanced_run_id = None
    for run in successful:
        run.quality = quality_label(run.recall_at_k)
        run.recommendation = tags_to_string(labels.get(run.id))
        tags = labels.get(run.id, [])
        if "best_recall" in tags:
            experiment.best_recall_run_id = run.id
        if "best_speed" in tags:
            experiment.best_speed_run_id = run.id
        if "best_balanced" in tags:
            experiment.best_balanced_run_id = run.id
    return selected


def execute_index_experiment(experiment_id: int, progress_cb=None) -> IndexExperiment:
    experiment = db.session.get(IndexExperiment, experiment_id)
    if not experiment:
        raise ValueError("实验不存在")
    if experiment.status not in ("pending", "running"):
        raise ExperimentConflict("实验当前状态不能运行")

    def _cb(progress: int, message: str):
        if progress_cb:
            progress_cb(max(0, min(100, progress)), message)

    experiment.status = "running"
    experiment.error_message = None
    db.session.commit()
    dataset = experiment.dataset
    vectors = load_vectors(dataset)
    n_cells = vectors.shape[0]
    sample_size = min(int(experiment.sample_size or 100), n_cells)
    rng = np.random.default_rng(int(experiment.seed or 42))
    sample_indices = rng.choice(np.arange(n_cells), size=sample_size, replace=False).tolist()

    _cb(5, "构建并预热 FAISS Flat 精确基线...")
    cache_dir = pathlib.Path(current_app.config["CACHE_DIR"])
    try:
        with tempfile.TemporaryDirectory(prefix="ann_exact_", dir=str(cache_dir)) as tmpdir:
            exact_path = pathlib.Path(tmpdir) / "faiss_flat.index"
            exact_info = build_backend_index(
                algorithm=FAISS_FLAT,
                vectors=vectors,
                metric=experiment.metric,
                index_path=exact_path,
                params={},
            )
            exact_loaded = load_backend_index(
                algorithm=FAISS_FLAT,
                metric=experiment.metric,
                dim=vectors.shape[1],
                index_path=exact_path,
                params=exact_info["params"],
            )
            exact_metrics = _benchmark_loaded_index(
                exact_loaded,
                vectors,
                sample_indices,
                experiment.top_k,
                experiment.repetitions or 3,
                experiment.warmup_count or 0,
            )
    except Exception as exc:
        experiment.status = "error"
        experiment.error_message = f"FAISS Flat 精确基线失败：{exc}"
        db.session.commit()
        raise

    experiment.exact_avg_query_time_ms = _round(exact_metrics["avg_query_time_ms"])
    experiment.exact_p95_query_time_ms = _round(exact_metrics["p95_query_time_ms"])
    db.session.commit()

    runs = list(experiment.runs)
    successful: list[IndexExperimentRun] = []
    for position, run in enumerate(runs, 1):
        start = 12 + int((position - 1) * 80 / max(len(runs), 1))
        span = max(1, int(80 / max(len(runs), 1)))
        run.status = "building"
        run.error_message = None
        db.session.commit()
        _cb(start, f"构建候选 {position}/{len(runs)}：{run.name}")
        try:
            index = build_ann_index(
                dataset_id=experiment.dataset_id,
                algorithm=run.algorithm,
                metric=experiment.metric,
                params=_json_object(run.params_json),
                source_experiment_id=experiment.id,
                source_run_id=run.id,
                lifecycle="candidate",
                progress_cb=lambda p, message, base=start, width=span: _cb(
                    base + int(width * 0.55 * p / 100), f"{run.name}：{message}"
                ),
            )
            run.build_time_ms = _round(index.build_time_ms, 3)
            run.index_size_bytes = index.index_size_bytes
            run.memory_bytes = index.index_size_bytes
            run.params_json = index.params_json
            run.status = "evaluating"
            db.session.commit()
            _cb(start + int(span * 0.60), f"真实评估 {position}/{len(runs)}：{run.name}")

            candidate_metrics = _benchmark_loaded_index(
                load_ann_backend(index, vectors.shape[1]),
                vectors,
                sample_indices,
                experiment.top_k,
                experiment.repetitions or 3,
                experiment.warmup_count or 0,
                exact_neighbors=exact_metrics["neighbors"],
            )
            avg_query = candidate_metrics["avg_query_time_ms"]
            run.recall_at_k = _round(candidate_metrics["recall_at_k"])
            run.avg_query_time_ms = _round(avg_query)
            run.p95_query_time_ms = _round(candidate_metrics["p95_query_time_ms"])
            run.avg_exact_time_ms = experiment.exact_avg_query_time_ms
            run.speedup = _round(experiment.exact_avg_query_time_ms / avg_query if avg_query > 0 else 0.0, 3)
            run.query_count = candidate_metrics["query_count"]
            run.status = "success"
            successful.append(run)
            db.session.commit()
        except Exception as exc:
            run.status = "error"
            run.error_message = str(exc)
            index = _index_for_run(run.id)
            if index:
                _discard_index_artifact(index)
            db.session.commit()

    recommended_ids = _update_selection_recommendations(experiment, successful)
    experiment.status = "ready_for_selection" if successful else "error"
    experiment.error_message = None if successful else "所有候选索引均构建或评估失败"
    result = {
        "recommended_run_ids": recommended_ids,
        "successful_count": len(successful),
    }
    experiment.result_json = json.dumps(result, ensure_ascii=False)
    db.session.commit()
    _cb(100, "候选索引构建与真实评估完成")
    return experiment


def run_index_experiment(
    dataset_id: int,
    metric: str = "l2",
    sample_size: int = 100,
    top_k: int = 10,
    candidate_keys: list[str] | None = None,
    progress_cb=None,
    seed: int = 42,
    repetitions: int = 3,
    warmup_count: int = 10,
    candidate_configs: list[dict] | None = None,
) -> IndexExperiment:
    experiment = create_index_experiment(
        dataset_id=dataset_id,
        metric=metric,
        sample_size=sample_size,
        top_k=top_k,
        seed=seed,
        repetitions=repetitions,
        warmup_count=warmup_count,
        candidate_configs=candidate_configs,
        candidate_keys=candidate_keys,
    )
    return execute_index_experiment(experiment.id, progress_cb=progress_cb)


def _stored_finalization(experiment: IndexExperiment) -> dict:
    return _json_object(experiment.result_json).get("finalization") or {}


def finalize_experiment(experiment_id: int, selected_run_ids: list[int]) -> dict:
    experiment = db.session.get(IndexExperiment, experiment_id)
    if not experiment:
        raise ValueError("实验不存在")
    selected_ids = list(dict.fromkeys(int(value) for value in selected_run_ids))
    if not 2 <= len(selected_ids) <= 3:
        raise ValueError("必须选择 2 到 3 个候选索引")

    if experiment.status == "finalized":
        stored_ids = [int(value) for value in _json_list(experiment.selected_run_ids_json)]
        if sorted(stored_ids) == sorted(selected_ids):
            return _stored_finalization(experiment)
        raise ExperimentConflict("实验已经完成选优，不能更换保留集合")
    if experiment.status != "ready_for_selection" or int(_workflow_config(experiment).get("workflow_version") or 1) < WORKFLOW_VERSION:
        raise ExperimentConflict("实验当前不可完成选优")

    run_map = {run.id: run for run in experiment.runs}
    selected_runs: list[IndexExperimentRun] = []
    selected_indexes: list[AnnIndex] = []
    for run_id in selected_ids:
        run = run_map.get(run_id)
        index = _index_for_run(run_id)
        if not run or run.status != "success" or float(run.recall_at_k or 0.0) < NOT_RECOMMENDED_RECALL:
            raise ValueError("只能保留评估成功且 Recall ≥ 0.80 的候选")
        if not index or index.status != "ready" or index.lifecycle not in ("candidate", "active"):
            raise ValueError("候选索引文件当前不可用")
        artifact_paths = [_safe_artifact_path(index.index_path)]
        if index.preprocess_path:
            artifact_paths.append(_safe_artifact_path(index.preprocess_path))
        if any(not path.exists() for path in artifact_paths):
            raise ValueError(f"候选索引 #{index.id} 的物理文件缺失")
        selected_runs.append(run)
        selected_indexes.append(index)

    selected_index_ids = {index.id for index in selected_indexes}
    cleanup_targets = {
        index.id: index for index in AnnIndex.query.filter_by(dataset_id=experiment.dataset_id).all()
        if index.id not in selected_index_ids and (index.lifecycle or "active") in ("active", "candidate")
    }
    for run, index in zip(selected_runs, selected_indexes):
        tags = [
            tag for tag in (run.recommendation or "").split(",")
            if tag in ("best_recall", "best_speed", "best_balanced", "acceptable_balanced")
        ]
        index.lifecycle = "active"
        index.status = "ready"
        index.selection_labels = ",".join(tags or ["manual"])
        index.discarded_at = None
        index.error_message = None

    for index in cleanup_targets.values():
        index.lifecycle = "discarded"
        index.discarded_at = datetime.utcnow()
    experiment.status = "finalized"
    experiment.selected_run_ids_json = json.dumps(selected_ids)
    experiment.finalized_at = datetime.utcnow()
    experiment.dataset.status = "indexed"
    db.session.commit()

    reclaimed = 0
    cleanup_errors: list[dict] = []
    discarded_ids: list[int] = []
    for index in cleanup_targets.values():
        removed, errors = _discard_index_artifact(index)
        reclaimed += removed
        discarded_ids.append(index.id)
        if errors:
            cleanup_errors.append({"index_id": index.id, "errors": errors})

    experiment.reclaimed_bytes = reclaimed
    finalization = {
        "active_indexes": [_index_payload(index) for index in selected_indexes],
        "selected_run_ids": selected_ids,
        "discarded_index_ids": discarded_ids,
        "reclaimed_bytes": reclaimed,
        "cleanup_errors": cleanup_errors,
    }
    result = _json_object(experiment.result_json)
    result["finalization"] = finalization
    experiment.result_json = json.dumps(result, ensure_ascii=False)
    db.session.commit()
    return finalization


def discard_experiment(experiment_id: int) -> dict:
    experiment = db.session.get(IndexExperiment, experiment_id)
    if not experiment:
        raise ValueError("实验不存在")
    if experiment.status == "finalized":
        raise ExperimentConflict("已完成选优的实验不能放弃")
    if experiment.status == "running":
        raise ExperimentConflict("运行中的实验暂不支持取消")

    reclaimed = 0
    errors: list[dict] = []
    indexes = AnnIndex.query.filter_by(source_experiment_id=experiment.id).all()
    for index in indexes:
        if index.lifecycle == "active":
            continue
        removed, next_errors = _discard_index_artifact(index)
        reclaimed += removed
        if next_errors:
            errors.append({"index_id": index.id, "errors": next_errors})
    experiment.status = "discarded"
    experiment.reclaimed_bytes = int(experiment.reclaimed_bytes or 0) + reclaimed
    db.session.commit()
    return {"discarded_index_ids": [index.id for index in indexes], "reclaimed_bytes": reclaimed, "cleanup_errors": errors}


def retry_experiment_cleanup(experiment_id: int) -> dict:
    experiment = db.session.get(IndexExperiment, experiment_id)
    if not experiment:
        raise ValueError("实验不存在")
    targets = AnnIndex.query.filter_by(dataset_id=experiment.dataset_id, lifecycle="discarded", status="cleanup_error").all()
    reclaimed = 0
    errors: list[dict] = []
    for index in targets:
        removed, next_errors = _discard_index_artifact(index)
        reclaimed += removed
        if next_errors:
            errors.append({"index_id": index.id, "errors": next_errors})
    experiment.reclaimed_bytes = int(experiment.reclaimed_bytes or 0) + reclaimed
    result = _json_object(experiment.result_json)
    if isinstance(result.get("finalization"), dict):
        result["finalization"]["reclaimed_bytes"] = int(experiment.reclaimed_bytes or 0)
        result["finalization"]["cleanup_errors"] = errors
        experiment.result_json = json.dumps(result, ensure_ascii=False)
    db.session.commit()
    return {"cleaned_index_ids": [index.id for index in targets if index.status == "deleted"], "reclaimed_bytes": reclaimed, "cleanup_errors": errors}
