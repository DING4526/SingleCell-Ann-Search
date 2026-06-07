"""后台任务执行模块：使用 ThreadPoolExecutor 在独立线程中执行耗时任务。"""
import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# 全局线程池，最多 2 个工作线程
executor = ThreadPoolExecutor(max_workers=2)


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


def run_process_task(task_id: int, dataset_id: int):
    """在线程中执行处理数据集任务。"""
    from app import create_app
    from app.extensions import db
    from app.models import Task
    from app.services.data_service import process_h5ad_dataset

    app = create_app()
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
                f"向量维度 {dataset.vector_dim}。"
            )
            task.result_json = json.dumps({
                "n_cells": dataset.n_cells,
                "n_genes": dataset.n_genes,
                "vector_dim": dataset.vector_dim,
                "status": dataset.status,
            }, ensure_ascii=False)
            task.updated_at = datetime.utcnow()
            db.session.commit()
        except Exception as e:
            task.status = "error"
            task.message = f"处理失败"
            task.error_message = f"{str(e)}\n{traceback.format_exc()}"
            task.updated_at = datetime.utcnow()
            db.session.commit()


def run_build_index_task(task_id: int, dataset_id: int, params: dict):
    """在线程中执行构建 HNSW 索引任务。"""
    from app import create_app
    from app.extensions import db
    from app.models import Task
    from app.services.ann_service import build_hnsw_index

    app = create_app()
    with app.app_context():
        task = db.session.get(Task, task_id)
        if not task:
            return
        task.status = "running"
        task.progress = 0
        task.message = "开始构建 HNSW 索引..."
        task.updated_at = datetime.utcnow()
        db.session.commit()

        def progress_cb(progress: int, message: str):
            task.progress = progress
            task.message = message
            task.updated_at = datetime.utcnow()
            db.session.commit()

        try:
            ann_index = build_hnsw_index(
                dataset_id,
                metric=params.get("metric", "l2"),
                M=params.get("M", 16),
                ef_construction=params.get("ef_construction", 200),
                ef_search=params.get("ef_search", 100),
                progress_cb=progress_cb,
            )
            task.status = "success"
            task.progress = 100
            task.message = (
                f"HNSW 索引构建完成（{ann_index.metric}, M={ann_index.M}），"
                f"耗时 {ann_index.build_time_ms:.1f} ms。"
            )
            task.result_json = json.dumps({
                "index_id": ann_index.id,
                "metric": ann_index.metric,
                "M": ann_index.M,
                "ef_construction": ann_index.ef_construction,
                "ef_search": ann_index.ef_search,
                "build_time_ms": ann_index.build_time_ms,
            }, ensure_ascii=False)
            task.updated_at = datetime.utcnow()
            db.session.commit()
        except Exception as e:
            task.status = "error"
            task.message = "索引构建失败"
            task.error_message = f"{str(e)}\n{traceback.format_exc()}"
            task.updated_at = datetime.utcnow()
            db.session.commit()
