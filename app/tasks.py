"""后台任务执行模块：使用 ThreadPoolExecutor 在独立线程中执行耗时任务。"""
import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# 全局线程池，最多 2 个工作线程
executor = ThreadPoolExecutor(max_workers=2)
# Keep expensive Plotly serialization out of the main task pool.
plot_executor = ThreadPoolExecutor(max_workers=1)


def _get_app():
    """获取当前 Flask 应用实例（支持从线程内调用）。"""
    from app import create_app
    return create_app()


def update_task(task_id: int, progress: int, message: str, status: str = None):
    """在线程内安全地更新 Task 记录。"""
    from app import create_app
    from app.extensions import db
    from app.models import Task

    app = create_app()
    with app.app_context():
        task = db.session.get(Task, task_id)
        if not task:
            return
        task.progress = progress
        task.message = message
        task.updated_at = datetime.utcnow()
        if status:
            task.status = status
        db.session.commit()


def run_process_task(task_id: int, dataset_id: int, app=None):
    """在线程中执行处理数据集任务。"""
    from app import create_app
    from app.extensions import db
    from app.models import Task
    from app.services.data_service import process_h5ad_dataset

    app = app or create_app()
    with app.app_context():
        task = db.session.get(Task, task_id)
        if not task:
            return
        task.status = "running"
        task.progress = 0
        task.message = "开始处理数据集..."
        task.updated_at = datetime.utcnow()
        db.session.commit()

        def progress_cb(progress: int, message: str):
            task.progress = progress
            task.message = message
            task.updated_at = datetime.utcnow()
            db.session.commit()

        try:
            dataset = process_h5ad_dataset(dataset_id, progress_cb=progress_cb)
            task.status = "success"
            task.progress = 100
            task.message = (
                f"处理完成：{dataset.n_cells} 个细胞，{dataset.n_genes} 个基因，"
                f"向量维度 {dataset.vector_dim}。下一步：构建 HNSW 索引"
            )
            task.result_json = json.dumps({
                "n_cells": dataset.n_cells,
                "n_genes": dataset.n_genes,
                "vector_dim": dataset.vector_dim,
                "status": dataset.status,
            }, ensure_ascii=False)
            task.updated_at = datetime.utcnow()
            db.session.commit()

            # 在同一 app context 内异步生成散点图缓存（不阻塞任务状态）
            try:
                from app.services.plot_service import generate_scatter_cache
                generate_scatter_cache(dataset_id)
            except Exception:
                pass  # 缓存生成失败不影响主流程，首次进入详情页时会重试
        except Exception as e:
            task.status = "error"
            task.message = f"处理失败"
            task.error_message = f"{str(e)}\n{traceback.format_exc()}"
            task.updated_at = datetime.utcnow()
            db.session.commit()


def run_build_index_task(task_id: int, dataset_id: int, params: dict, app=None):
    """在线程中执行构建 ANN 索引任务。"""
    from app import create_app
    from app.extensions import db
    from app.models import Task
    from app.services.ann_service import build_ann_index

    app = app or create_app()
    with app.app_context():
        task = db.session.get(Task, task_id)
        if not task:
            return
        task.status = "running"
        task.progress = 0
        task.message = "开始构建 ANN 索引..."
        task.updated_at = datetime.utcnow()
        db.session.commit()

        def progress_cb(progress: int, message: str):
            task.progress = progress
            task.message = message
            task.updated_at = datetime.utcnow()
            db.session.commit()

        try:
            ann_index = build_ann_index(
                dataset_id,
                algorithm=params.get("algorithm", "hnswlib_hnsw"),
                metric=params.get("metric", "l2"),
                params=params.get("params", {}),
                M=params.get("M"),
                ef_construction=params.get("ef_construction"),
                ef_search=params.get("ef_search"),
                source_experiment_id=params.get("source_experiment_id"),
                source_run_id=params.get("source_run_id"),
                progress_cb=progress_cb,
            )
            task.status = "success"
            task.progress = 100
            task.message = (
                f"ANN 索引构建完成（{ann_index.algorithm}, {ann_index.metric}），"
                f"耗时 {ann_index.build_time_ms:.1f} ms。可继续运行真实索引评估"
            )
            task.result_json = json.dumps({
                "index_id": ann_index.id,
                "algorithm": ann_index.algorithm,
                "metric": ann_index.metric,
                "source_experiment_id": ann_index.source_experiment_id,
                "source_run_id": ann_index.source_run_id,
                "M": ann_index.M,
                "ef_construction": ann_index.ef_construction,
                "ef_search": ann_index.ef_search,
                "build_time_ms": ann_index.build_time_ms,
                "index_size_bytes": ann_index.index_size_bytes,
            }, ensure_ascii=False)
            task.updated_at = datetime.utcnow()
            db.session.commit()

            # 索引构建完成后刷新散点图缓存（强制重新生成）
            try:
                from app.services.plot_service import generate_scatter_cache
                generate_scatter_cache(dataset_id)
            except Exception:
                pass  # 缓存失败不影响主流程

        except Exception as e:
            task.status = "error"
            task.message = "索引构建失败"
            task.error_message = f"{str(e)}\n{traceback.format_exc()}"
            task.updated_at = datetime.utcnow()
            db.session.commit()


def run_search_task(task_id: int, params: dict, app=None):
    """在线程中执行单数据集检索任务。"""
    from app import create_app
    from app.extensions import db
    from app.models import Task
    from app.services.search_service import execute_single_search

    app = app or create_app()
    with app.app_context():
        task = db.session.get(Task, task_id)
        if not task:
            return
        task.status = "running"
        task.progress = 5
        task.message = "开始检索..."
        task.updated_at = datetime.utcnow()
        db.session.commit()

        def progress_cb(progress: int, message: str):
            task.progress = progress
            task.message = message
            task.updated_at = datetime.utcnow()
            db.session.commit()

        try:
            payload = execute_single_search(
                dataset_id=params["dataset_id"],
                index_id=params["index_id"],
                query_cell_index=params["query_cell_index"],
                top_k=params.get("top_k", 10),
                filter_cell_type=params.get("filter_cell_type"),
                include_plot=False,
                progress_cb=progress_cb,
            )
            result_count = len(payload["result_data"].get("results", []))
            query_time_ms = payload["result_data"].get("query_time_ms")
            task.status = "success"
            task.progress = 100
            task.message = f"检索完成：返回 {result_count} 个细胞，ANN 查询耗时 {query_time_ms} ms。"
            task.result_json = json.dumps(payload, ensure_ascii=False)
            task.updated_at = datetime.utcnow()
            db.session.commit()
        except Exception as e:
            task.status = "error"
            task.message = "检索失败"
            task.error_message = f"{str(e)}\n{traceback.format_exc()}"
            task.updated_at = datetime.utcnow()
            db.session.commit()


def run_search_plot_task(task_id: int, params: dict, app=None):
    """在线程中生成单数据集检索高亮图。"""
    from app import create_app
    from app.extensions import db
    from app.models import Task
    from app.services.search_service import execute_search_plot

    app = app or create_app()
    with app.app_context():
        task = db.session.get(Task, task_id)
        if not task:
            return
        task.status = "running"
        task.progress = 5
        task.message = "开始生成检索高亮图..."
        task.updated_at = datetime.utcnow()
        db.session.commit()

        def progress_cb(progress: int, message: str):
            task.progress = progress
            task.message = message
            task.updated_at = datetime.utcnow()
            db.session.commit()

        try:
            payload = execute_search_plot(
                dataset_id=params["dataset_id"],
                query_cell_index=params["query_cell_index"],
                result_cell_indices=params.get("result_cell_indices", []),
                max_background_points=params.get("max_background_points", 8_000),
                progress_cb=progress_cb,
            )
            task.status = "success"
            task.progress = 100
            task.message = "检索高亮图生成完成。"
            task.result_json = json.dumps(payload, ensure_ascii=False)
            task.updated_at = datetime.utcnow()
            db.session.commit()
        except Exception as e:
            task.status = "error"
            task.message = "检索高亮图生成失败"
            task.error_message = f"{str(e)}\n{traceback.format_exc()}"
            task.updated_at = datetime.utcnow()
            db.session.commit()


def run_multi_search_task(task_id: int, params: dict, app=None):
    """在线程中执行跨数据集检索任务。"""
    from app import create_app
    from app.extensions import db
    from app.models import Task
    from app.services.multi_search_service import search_across_datasets

    app = app or create_app()
    with app.app_context():
        task = db.session.get(Task, task_id)
        if not task:
            return
        task.status = "running"
        task.progress = 10
        task.message = "开始跨数据集检索..."
        task.updated_at = datetime.utcnow()
        db.session.commit()

        try:
            result_data = search_across_datasets(
                source_dataset_id=params["dataset_id"],
                source_index_id=params["index_id"],
                query_cell_index=params["query_cell_index"],
                top_k=params.get("top_k", 20),
                target_dataset_ids=params.get("target_dataset_ids"),
            )
            task.status = "success"
            task.progress = 100
            task.message = (
                f"跨数据集检索完成：检索 {result_data.get('searched_dataset_count', 0)} 个数据集，"
                f"返回 {len(result_data.get('results', []))} 个细胞。"
            )
            task.result_json = json.dumps({"result_data": result_data}, ensure_ascii=False)
            task.updated_at = datetime.utcnow()
            db.session.commit()
        except Exception as e:
            task.status = "error"
            task.message = "跨数据集检索失败"
            task.error_message = f"{str(e)}\n{traceback.format_exc()}"
            task.updated_at = datetime.utcnow()
            db.session.commit()


def run_index_experiment_task(task_id: int, params: dict, app=None):
    """Build and evaluate all persistent candidates in one background task."""
    from app import create_app
    from app.extensions import db
    from app.models import Task
    from app.services.index_experiment_service import execute_index_experiment, experiment_to_dict, run_index_experiment

    app = app or create_app()
    with app.app_context():
        task = db.session.get(Task, task_id)
        if not task:
            return
        task.status = "running"
        task.progress = 5
        task.message = "开始构建并评估候选索引..."
        task.updated_at = datetime.utcnow()
        db.session.commit()

        def progress_cb(progress: int, message: str):
            task.progress = progress
            task.message = message
            task.updated_at = datetime.utcnow()
            db.session.commit()

        try:
            if params.get("experiment_id"):
                experiment = execute_index_experiment(params["experiment_id"], progress_cb=progress_cb)
            else:
                experiment = run_index_experiment(
                    dataset_id=params["dataset_id"],
                    metric=params.get("metric", "l2"),
                    sample_size=params.get("sample_size", 100),
                    top_k=params.get("top_k", 10),
                    candidate_keys=params.get("candidate_keys"),
                    seed=params.get("seed", 42),
                    repetitions=params.get("repetitions", 3),
                    warmup_count=params.get("warmup_count", 10),
                    candidate_configs=params.get("candidate_configs"),
                    progress_cb=progress_cb,
                )
            payload = {"experiment": experiment_to_dict(experiment)}
            task.status = "success"
            task.progress = 100
            task.message = f"候选索引构建与真实评估完成：{experiment.candidate_count} 个候选。"
            task.result_json = json.dumps(payload, ensure_ascii=False)
            task.updated_at = datetime.utcnow()
            db.session.commit()
        except Exception as e:
            task.status = "error"
            task.message = "候选索引实验失败"
            task.error_message = f"{str(e)}\n{traceback.format_exc()}"
            task.updated_at = datetime.utcnow()
            db.session.commit()


def run_index_evaluation_task(task_id: int, params: dict, app=None):
    """Evaluate one persisted ANN index in a background thread."""
    from app import create_app
    from app.extensions import db
    from app.models import Task
    from app.services.index_evaluation_service import index_evaluation_to_dict, run_index_evaluation

    app = app or create_app()
    with app.app_context():
        task = db.session.get(Task, task_id)
        if not task:
            return
        task.status = "running"
        task.progress = 5
        task.message = "开始运行真实索引评估..."
        task.updated_at = datetime.utcnow()
        db.session.commit()

        def progress_cb(progress: int, message: str):
            task.progress = progress
            task.message = message
            task.updated_at = datetime.utcnow()
            db.session.commit()

        try:
            evaluation = run_index_evaluation(
                dataset_id=params["dataset_id"],
                index_id=params["index_id"],
                sample_size=params.get("sample_size", 100),
                top_k=params.get("top_k", 10),
                seed=params.get("seed", 42),
                progress_cb=progress_cb,
            )
            payload = {"evaluation": index_evaluation_to_dict(evaluation)}
            task.status = "success"
            task.progress = 100
            task.message = f"真实索引评估完成：Recall@{evaluation.top_k} {evaluation.recall_at_k:.1%}。"
            task.result_json = json.dumps(payload, ensure_ascii=False)
            task.updated_at = datetime.utcnow()
            db.session.commit()
        except Exception as e:
            task.status = "error"
            task.message = "真实索引评估失败"
            task.error_message = f"{str(e)}\n{traceback.format_exc()}"
            task.updated_at = datetime.utcnow()
            db.session.commit()


def run_build_joint_index_task(task_id: int, params: dict, app=None):
    """Build a Harmony-corrected physical joint index in a background thread."""
    from app import create_app
    from app.extensions import db
    from app.models import Task
    from app.services.joint_index_service import build_joint_index, joint_index_to_dict

    app = app or create_app()
    with app.app_context():
        task = db.session.get(Task, task_id)
        if not task:
            return
        task.status = "running"
        task.progress = 5
        task.message = "开始构建联合索引..."
        task.updated_at = datetime.utcnow()
        db.session.commit()

        def progress_cb(progress: int, message: str):
            task.progress = progress
            task.message = message
            task.updated_at = datetime.utcnow()
            db.session.commit()

        try:
            joint_index = build_joint_index(
                name=params.get("name") or "联合索引",
                dataset_ids=params["dataset_ids"],
                metric=params.get("metric", "l2"),
                M=params.get("M", 16),
                ef_construction=params.get("ef_construction", 200),
                ef_search=params.get("ef_search", 100),
                n_pcs=params.get("n_pcs", 50),
                n_top_genes=params.get("n_top_genes", 2000),
                min_common_genes=params.get("min_common_genes", 500),
                owner_id=params.get("owner_id"),
                progress_cb=progress_cb,
            )
            task.status = "success"
            task.progress = 100
            task.message = f"联合索引构建完成：纳入 {joint_index.n_cells} 个细胞，共同基因 {joint_index.common_gene_count} 个。"
            task.result_json = json.dumps({"joint_index": joint_index_to_dict(joint_index)}, ensure_ascii=False)
            task.updated_at = datetime.utcnow()
            db.session.commit()
        except Exception as e:
            task.status = "error"
            task.message = "联合索引构建失败"
            task.error_message = f"{str(e)}\n{traceback.format_exc()}"
            task.updated_at = datetime.utcnow()
            db.session.commit()


def run_joint_search_task(task_id: int, params: dict, app=None):
    """Search a physical joint index in a background thread."""
    from app import create_app
    from app.extensions import db
    from app.models import Task
    from app.services.joint_index_service import search_joint_index

    app = app or create_app()
    with app.app_context():
        task = db.session.get(Task, task_id)
        if not task:
            return
        task.status = "running"
        task.progress = 20
        task.message = "开始联合索引检索..."
        task.updated_at = datetime.utcnow()
        db.session.commit()

        try:
            result_data = search_joint_index(
                joint_index_id=params["joint_index_id"],
                query_dataset_id=params["query_dataset_id"],
                query_cell_index=params["query_cell_index"],
                top_k=params.get("top_k", 20),
            )
            task.status = "success"
            task.progress = 100
            task.message = f"联合检索完成：返回 {len(result_data.get('results', []))} 个细胞。"
            task.result_json = json.dumps({"result_data": result_data}, ensure_ascii=False)
            task.updated_at = datetime.utcnow()
            db.session.commit()
        except Exception as e:
            task.status = "error"
            task.message = "联合检索失败"
            task.error_message = f"{str(e)}\n{traceback.format_exc()}"
            task.updated_at = datetime.utcnow()
            db.session.commit()


def run_joint_search_plot_task(task_id: int, params: dict, app=None):
    """Generate a joint-index Harmony UMAP highlight plot in a background thread."""
    from app import create_app
    from app.extensions import db
    from app.models import Task
    from app.services.joint_index_service import joint_search_plot

    app = app or create_app()
    with app.app_context():
        task = db.session.get(Task, task_id)
        if not task:
            return
        task.status = "running"
        task.progress = 15
        task.message = "开始生成联合高亮图..."
        task.updated_at = datetime.utcnow()
        db.session.commit()

        try:
            payload = joint_search_plot(
                joint_index_id=params["joint_index_id"],
                query_global_label=params["query_global_label"],
                result_global_labels=params.get("result_global_labels", []),
                max_background_points=params.get("max_background_points", 12_000),
            )
            task.status = "success"
            task.progress = 100
            task.message = "联合高亮图生成完成。"
            task.result_json = json.dumps(payload, ensure_ascii=False)
            task.updated_at = datetime.utcnow()
            db.session.commit()
        except Exception as e:
            task.status = "error"
            task.message = "联合高亮图生成失败"
            task.error_message = f"{str(e)}\n{traceback.format_exc()}"
            task.updated_at = datetime.utcnow()
            db.session.commit()
