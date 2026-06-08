"""API 蓝图：提供 JSON 格式的 AJAX 接口，用于非阻塞操作。"""
import os
import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required
from werkzeug.utils import secure_filename
from app.extensions import db
from app.models import Dataset, AnnIndex, Cell, Task
from app.tasks import executor, run_process_task, run_build_index_task

api_bp = Blueprint("api", __name__, url_prefix="/api")


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _task_to_dict(task: Task) -> dict:
    """将 Task 对象序列化为字典。"""
    import json
    result = None
    if task.result_json:
        try:
            result = json.loads(task.result_json)
        except Exception:
            result = task.result_json
    return {
        "id": task.id,
        "type": task.type,
        "status": task.status,
        "progress": task.progress,
        "message": task.message,
        "error": task.error_message,
        "result": result,
        "dataset_id": task.dataset_id,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


# ---------------------------------------------------------------------------
# 数据集上传
# ---------------------------------------------------------------------------

@api_bp.route("/datasets/upload", methods=["POST"])
@login_required
def api_upload():
    """AJAX 上传 .h5ad 文件，返回 JSON。"""
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify(ok=False, message="未选择文件。"), 400
    if not file.filename.endswith(".h5ad"):
        return jsonify(ok=False, message="仅支持 .h5ad 格式的文件。"), 400

    filename = secure_filename(file.filename)
    # 使用 时间戳+UUID 前缀保证磁盘文件名唯一，避免同名覆盖
    unique_prefix = datetime.now().strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:8] + "_"
    disk_filename = unique_prefix + filename
    file_path = os.path.join(current_app.config["RAW_DIR"], disk_filename)
    file.save(file_path)

    name = request.form.get("name", "").strip() or filename.replace(".h5ad", "")
    description = request.form.get("description", "").strip()

    dataset = Dataset(
        name=name,
        description=description,
        file_path=file_path,
        status="uploaded",
    )
    db.session.add(dataset)
    db.session.commit()

    return jsonify(
        ok=True,
        dataset_id=dataset.id,
        message=f"数据集「{name}」上传成功，请点击「处理数据集」提取向量。",
        redirect_url=f"/datasets/{dataset.id}",
    )


# ---------------------------------------------------------------------------
# 数据集处理（异步任务）
# ---------------------------------------------------------------------------

@api_bp.route("/datasets/<int:dataset_id>/process", methods=["POST"])
@login_required
def api_process(dataset_id):
    """异步处理数据集，立即返回 task_id。"""
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        return jsonify(ok=False, message="数据集不存在。"), 404

    task = Task(
        type="process",
        status="pending",
        progress=0,
        message="任务已提交，等待执行...",
        dataset_id=dataset_id,
        updated_at=datetime.utcnow(),
    )
    db.session.add(task)
    db.session.commit()

    executor.submit(run_process_task, task.id, dataset_id)
    return jsonify(ok=True, task_id=task.id)


# ---------------------------------------------------------------------------
# 构建 HNSW 索引（异步任务）
# ---------------------------------------------------------------------------

@api_bp.route("/datasets/<int:dataset_id>/build-index", methods=["POST"])
@login_required
def api_build_index(dataset_id):
    """异步构建 HNSW 索引，立即返回 task_id。"""
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        return jsonify(ok=False, message="数据集不存在。"), 404

    if dataset.status not in ("processed", "indexed"):
        return jsonify(ok=False, message="数据集需要先完成处理才能构建索引。"), 400

    params = {
        "metric": request.form.get("metric", "l2"),
        "M": int(request.form.get("M", 16)),
        "ef_construction": int(request.form.get("ef_construction", 200)),
        "ef_search": int(request.form.get("ef_search", 100)),
    }

    task = Task(
        type="build_index",
        status="pending",
        progress=0,
        message="任务已提交，等待执行...",
        dataset_id=dataset_id,
        updated_at=datetime.utcnow(),
    )
    db.session.add(task)
    db.session.commit()

    executor.submit(run_build_index_task, task.id, dataset_id, params)
    return jsonify(ok=True, task_id=task.id)


# ---------------------------------------------------------------------------
# 查询任务状态
# ---------------------------------------------------------------------------

@api_bp.route("/tasks/<int:task_id>", methods=["GET"])
@login_required
def api_task_status(task_id):
    """查询后台任务状态与进度。"""
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify(ok=False, message="任务不存在。"), 404
    return jsonify(ok=True, **_task_to_dict(task))


# ---------------------------------------------------------------------------
# AJAX 检索（同步，直接返回结果）
# ---------------------------------------------------------------------------

@api_bp.route("/search", methods=["POST"])
@login_required
def api_search():
    """AJAX 检索：执行 Top-K 相似细胞检索，返回结果及 Plotly JSON 图数据。"""
    from app.services.ann_service import search_by_cell_index
    from app.services.plot_service import search_scatter_json

    dataset_id = int(request.form.get("dataset_id", 0))
    raw_index_id = request.form.get("index_id", "").strip()
    if not raw_index_id:
        return jsonify(ok=False, message="请先选择可用索引。"), 400
    index_id = int(raw_index_id)
    query_cell_index = int(request.form.get("query_cell_index", 0))
    top_k = int(request.form.get("top_k", 10))
    filter_cell_type = request.form.get("filter_cell_type", "").strip() or None

    try:
        result_data = search_by_cell_index(
            dataset_id=dataset_id,
            index_id=index_id,
            query_cell_index=query_cell_index,
            top_k=top_k,
            filter_cell_type=filter_cell_type,
        )
        result_cell_indices = [r["cell_index"] for r in result_data["results"]]
        scatter_plot = search_scatter_json(dataset_id, query_cell_index, result_cell_indices)
        return jsonify(ok=True, result_data=result_data, scatter_plot=scatter_plot)
    except Exception as e:
        return jsonify(ok=False, message=f"检索失败：{str(e)}"), 500


# ---------------------------------------------------------------------------
# AJAX 评估（同步，直接返回结果）
# ---------------------------------------------------------------------------

@api_bp.route("/evaluate", methods=["POST"])
@login_required
def api_evaluate():
    """AJAX 评估：对比 ANN 与精确检索，返回指标及 Plotly JSON 图数据。"""
    from app.services.eval_service import evaluate_index
    from app.services.plot_service import eval_bar_json

    dataset_id = int(request.form.get("dataset_id", 0))
    raw_index_id = request.form.get("index_id", "").strip()
    if not raw_index_id:
        return jsonify(ok=False, message="请先选择可用索引。"), 400
    index_id = int(raw_index_id)
    sample_size = int(request.form.get("sample_size", 10))
    top_k = int(request.form.get("eval_top_k", 10))

    try:
        metrics = evaluate_index(dataset_id, index_id, sample_size=sample_size, top_k=top_k)
        bar_plot = eval_bar_json(metrics)
        return jsonify(ok=True, metrics=metrics, bar_plot=bar_plot)
    except Exception as e:
        return jsonify(ok=False, message=f"评估失败：{str(e)}"), 500


# ---------------------------------------------------------------------------
# 获取数据集最新状态（局部刷新）
# ---------------------------------------------------------------------------

@api_bp.route("/datasets/<int:dataset_id>/status", methods=["GET"])
@login_required
def api_dataset_status(dataset_id):
    """返回数据集最新状态信息，用于前端局部更新。"""
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        return jsonify(ok=False, message="数据集不存在。"), 404

    indexes = AnnIndex.query.filter_by(dataset_id=dataset_id, status="ready").all()
    return jsonify(
        ok=True,
        status=dataset.status,
        n_cells=dataset.n_cells,
        n_genes=dataset.n_genes,
        vector_dim=dataset.vector_dim,
        error_message=dataset.error_message,
        indexes=[
            {
                "id": idx.id,
                "metric": idx.metric,
                "M": idx.M,
                "ef_construction": idx.ef_construction,
                "ef_search": idx.ef_search,
                "build_time_ms": idx.build_time_ms,
                "status": idx.status,
            }
            for idx in indexes
        ],
    )


# ---------------------------------------------------------------------------
# 获取数据集 cell_type 列表（检索页数据集切换时动态更新）
# ---------------------------------------------------------------------------

@api_bp.route("/datasets/<int:dataset_id>/cell-types", methods=["GET"])
@login_required
def api_cell_types(dataset_id):
    """返回数据集中所有 cell_type 值，用于检索页过滤器动态更新。"""
    types = (
        db.session.query(Cell.cell_type)
        .filter(Cell.dataset_id == dataset_id, Cell.cell_type.isnot(None))
        .distinct()
        .all()
    )
    cell_types = sorted(set(t[0] for t in types if t[0]))
    return jsonify(ok=True, cell_types=cell_types)


# ---------------------------------------------------------------------------
# 获取数据集散点图缓存（异步加载，避免详情页阻塞）
# ---------------------------------------------------------------------------

@api_bp.route("/datasets/<int:dataset_id>/scatter", methods=["GET"])
@login_required
def api_dataset_scatter(dataset_id):
    """返回数据集全量细胞散点图的 Plotly JSON。
    优先读取磁盘缓存；若缓存不存在则同步生成后返回。
    """
    import pathlib
    from app.services.plot_service import generate_scatter_cache

    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        return jsonify(ok=False, message="数据集不存在。"), 404

    if dataset.status not in ("processed", "indexed"):
        return jsonify(ok=False, message="数据集尚未处理完成，暂无散点图。"), 400

    cache_dir = pathlib.Path(current_app.config["CACHE_DIR"])

    # 若已有有效缓存文件，直接读取返回
    if dataset.scatter_cache_path:
        cache_path = cache_dir / dataset.scatter_cache_path
        if cache_path.exists():
            import json as _json
            with open(cache_path, "r", encoding="utf-8") as f:
                scatter_plot = _json.load(f)
            return jsonify(ok=True, scatter_plot=scatter_plot)

    # 缓存不存在，生成后返回
    try:
        generate_scatter_cache(dataset_id)
        # 重新读取刚写入的缓存
        dataset = db.session.get(Dataset, dataset_id)
        cache_path = cache_dir / dataset.scatter_cache_path
        import json as _json
        with open(cache_path, "r", encoding="utf-8") as f:
            scatter_plot = _json.load(f)
        return jsonify(ok=True, scatter_plot=scatter_plot)
    except Exception as e:
        return jsonify(ok=False, message=f"散点图生成失败：{str(e)}"), 500


# ---------------------------------------------------------------------------
# 获取进行中的任务列表（全局任务指示器 + 最近任务）
# ---------------------------------------------------------------------------

@api_bp.route("/tasks/active", methods=["GET"])
@login_required
def api_active_tasks():
    """返回所有进行中（pending/running）的任务列表。"""
    tasks = (
        Task.query
        .filter(Task.status.in_(["pending", "running"]))
        .order_by(Task.updated_at.desc())
        .all()
    )
    return jsonify(ok=True, tasks=[_task_to_dict(t) for t in tasks])


# ---------------------------------------------------------------------------
# 获取单个细胞元信息（检索页索引预览）
# ---------------------------------------------------------------------------

@api_bp.route("/datasets/<int:dataset_id>/cell-meta/<int:cell_index>", methods=["GET"])
@login_required
def api_cell_meta(dataset_id, cell_index):
    """返回指定数据集中某个细胞的元信息，用于检索页输入索引后预览。"""
    cell = Cell.query.filter_by(
        dataset_id=dataset_id, cell_index=cell_index
    ).first()
    if not cell:
        return jsonify(ok=False, message="细胞索引不存在。"), 404
    return jsonify(
        ok=True,
        cell={
            "cell_index": cell.cell_index,
            "cell_name": cell.cell_name,
            "cell_type": cell.cell_type,
            "disease": cell.disease,
            "age_group": cell.age_group,
        },
    )


# ---------------------------------------------------------------------------
# 仪表盘聚合数据（工作台页面）
# ---------------------------------------------------------------------------

@api_bp.route("/dashboard/summary", methods=["GET"])
@login_required
def api_dashboard_summary():
    """返回工作台页面所需的聚合统计数据。"""
    from app.models import QueryLog

    datasets = Dataset.query.order_by(Dataset.created_at.desc()).all()
    datasets_total = len(datasets)
    datasets_uploaded = sum(1 for d in datasets if d.status == "uploaded")
    datasets_processed = sum(1 for d in datasets if d.status == "processed")
    datasets_indexed = sum(1 for d in datasets if d.status == "indexed")
    indexes_total = AnnIndex.query.filter_by(status="ready").count()
    recent_queries = QueryLog.query.count()

    recent_datasets = [
        {
            "id": d.id,
            "name": d.name,
            "status": d.status,
            "n_cells": d.n_cells,
            "created_at": d.created_at.strftime("%Y-%m-%d %H:%M") if d.created_at else "",
        }
        for d in datasets[:5]
    ]

    recent_tasks = [
        _task_to_dict(t)
        for t in Task.query.order_by(Task.updated_at.desc()).limit(5).all()
    ]

    first_uploaded = next((d.id for d in datasets if d.status == "uploaded"), None)
    first_processed = next((d.id for d in datasets if d.status == "processed"), None)

    return jsonify(
        ok=True,
        datasets_total=datasets_total,
        datasets_uploaded=datasets_uploaded,
        datasets_processed=datasets_processed,
        datasets_indexed=datasets_indexed,
        indexes_total=indexes_total,
        recent_queries=recent_queries,
        recent_datasets=recent_datasets,
        recent_tasks=recent_tasks,
        first_uploaded_id=first_uploaded,
        first_processed_id=first_processed,
    )
