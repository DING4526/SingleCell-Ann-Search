"""API 蓝图：提供 JSON 格式的 AJAX 接口，用于非阻塞操作。"""
import os
import uuid
import pathlib
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user, login_user, logout_user
from werkzeug.utils import secure_filename
from app.extensions import db
from app.models import Dataset, AnnIndex, Cell, Task, QueryLog, User
from app.tasks import executor, run_process_task, run_build_index_task, run_search_task, run_multi_search_task
from app.services.access_service import (
    accessible_datasets_query,
    accessible_tasks_query,
    can_manage_dataset,
    can_view_dataset,
    is_admin,
)

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
    dataset_name = None
    if task.dataset_id:
        ds = db.session.get(Dataset, task.dataset_id)
        if ds:
            dataset_name = ds.name
    return {
        "id": task.id,
        "type": task.type,
        "status": task.status,
        "progress": task.progress,
        "message": task.message,
        "error": task.error_message,
        "result": result,
        "dataset_id": task.dataset_id,
        "dataset_name": dataset_name,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


def _int_form(name: str, default: int, min_value: int = None, max_value: int = None) -> int:
    """读取并约束表单中的整数参数。"""
    raw = request.form.get(name, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{name} 必须是整数")
    if min_value is not None and value < min_value:
        raise ValueError(f"{name} 不能小于 {min_value}")
    if max_value is not None and value > max_value:
        raise ValueError(f"{name} 不能大于 {max_value}")
    return value


def _index_to_dict(idx: AnnIndex) -> dict:
    return {
        "id": idx.id,
        "dataset_id": idx.dataset_id,
        "algorithm": "HNSW",
        "metric": idx.metric,
        "M": idx.M,
        "ef_construction": idx.ef_construction,
        "ef_search": idx.ef_search,
        "build_time_ms": idx.build_time_ms,
        "status": idx.status,
        "created_at": idx.created_at.isoformat() if idx.created_at else None,
    }


def _dataset_to_dict(dataset: Dataset, include_indexes: bool = True) -> dict:
    data = {
        "id": dataset.id,
        "name": dataset.name,
        "description": dataset.description or "",
        "n_cells": dataset.n_cells,
        "n_genes": dataset.n_genes,
        "vector_dim": dataset.vector_dim,
        "status": dataset.status,
        "error_message": dataset.error_message,
        "owner_id": dataset.owner_id,
        "owner_name": dataset.owner.username if dataset.owner else None,
        "visibility": dataset.visibility or "private",
        "created_at": dataset.created_at.isoformat() if dataset.created_at else None,
        "can_manage": can_manage_dataset(dataset),
    }
    if include_indexes:
        data["indexes"] = [_index_to_dict(idx) for idx in dataset.indexes]
        data["ready_index_count"] = sum(1 for idx in dataset.indexes if idx.status == "ready")
    return data


def _dataset_stats(dataset_id: int) -> dict:
    stats = {}
    for col in ["cell_type", "disease", "age_group"]:
        rows = (
            db.session.query(getattr(Cell, col), db.func.count(Cell.id))
            .filter(Cell.dataset_id == dataset_id)
            .group_by(getattr(Cell, col))
            .order_by(db.func.count(Cell.id).desc())
            .all()
        )
        stats[col] = [{"name": key or "N/A", "count": count} for key, count in rows]
    return stats


def _delete_dataset_files(dataset: Dataset):
    dataset_id = dataset.id
    if dataset.file_path:
        other_refs = Dataset.query.filter(
            Dataset.id != dataset_id,
            Dataset.file_path == dataset.file_path,
        ).count()
        if other_refs == 0 and os.path.exists(dataset.file_path):
            os.remove(dataset.file_path)

    if dataset.vector_path:
        vec_path = pathlib.Path(current_app.config["CACHE_DIR"]) / dataset.vector_path
        if vec_path.exists():
            os.remove(str(vec_path))

    if dataset.scatter_cache_path:
        scatter_path = pathlib.Path(current_app.config["CACHE_DIR"]) / dataset.scatter_cache_path
        if scatter_path.exists():
            os.remove(str(scatter_path))

    for idx in AnnIndex.query.filter_by(dataset_id=dataset_id).all():
        idx_path = pathlib.Path(current_app.config["INDEX_DIR"]) / idx.index_path
        if idx_path.exists():
            os.remove(str(idx_path))


# ---------------------------------------------------------------------------
# SPA 认证接口
# ---------------------------------------------------------------------------

@api_bp.route("/auth/me", methods=["GET"])
def api_auth_me():
    if not current_user.is_authenticated:
        return jsonify(ok=True, authenticated=False, user=None)
    return jsonify(
        ok=True,
        authenticated=True,
        user={
            "id": current_user.id,
            "username": current_user.username,
            "role": current_user.role,
            "is_admin": is_admin(),
        },
    )


@api_bp.route("/auth/login", methods=["POST"])
def api_auth_login():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    user = User.query.filter_by(username=username).first()
    if user is None or not user.check_password(password):
        return jsonify(ok=False, message="用户名或密码错误。"), 401
    login_user(user, remember=True)
    return jsonify(ok=True, message="登录成功。", user={
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "is_admin": user.role == "admin",
    })


@api_bp.route("/auth/register", methods=["POST"])
def api_auth_register():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    confirm = request.form.get("confirm", "")

    if not username or not password:
        return jsonify(ok=False, message="用户名和密码不能为空。"), 400
    if len(password) < 4:
        return jsonify(ok=False, message="密码长度至少为 4 位。"), 400
    if password != confirm:
        return jsonify(ok=False, message="两次输入的密码不一致。"), 400
    if User.query.filter_by(username=username).first():
        return jsonify(ok=False, message="用户名已存在。"), 400

    user = User(username=username)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    login_user(user, remember=True)
    return jsonify(ok=True, message="注册成功。", user={
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "is_admin": False,
    })


@api_bp.route("/auth/logout", methods=["POST"])
@login_required
def api_auth_logout():
    logout_user()
    return jsonify(ok=True, message="已退出登录。")


# ---------------------------------------------------------------------------
# SPA 数据集资源接口
# ---------------------------------------------------------------------------

@api_bp.route("/datasets", methods=["GET"])
@login_required
def api_datasets():
    datasets = accessible_datasets_query().order_by(Dataset.created_at.desc()).all()
    return jsonify(ok=True, datasets=[_dataset_to_dict(ds) for ds in datasets])


@api_bp.route("/datasets/<int:dataset_id>", methods=["GET"])
@login_required
def api_dataset_detail(dataset_id):
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        return jsonify(ok=False, message="数据集不存在。"), 404
    if not can_view_dataset(dataset):
        return jsonify(ok=False, message="没有权限查看该数据集。"), 403

    tasks = (
        Task.query.filter_by(dataset_id=dataset_id)
        .order_by(Task.updated_at.desc())
        .limit(8)
        .all()
    )
    return jsonify(
        ok=True,
        dataset=_dataset_to_dict(dataset),
        stats=_dataset_stats(dataset_id) if dataset.status in ("processed", "indexed") else {},
        recent_tasks=[_task_to_dict(task) for task in tasks],
    )


@api_bp.route("/datasets/<int:dataset_id>", methods=["DELETE"])
@login_required
def api_dataset_delete(dataset_id):
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        return jsonify(ok=False, message="数据集不存在。"), 404
    if not can_manage_dataset(dataset):
        return jsonify(ok=False, message="没有权限删除该数据集。"), 403

    _delete_dataset_files(dataset)
    db.session.delete(dataset)
    db.session.commit()
    return jsonify(ok=True, message="数据集已删除。")


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
        owner_id=current_user.id,
        visibility="private",
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
    if not can_manage_dataset(dataset):
        return jsonify(ok=False, message="没有权限处理该数据集。"), 403

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

    executor.submit(run_process_task, task.id, dataset_id, current_app._get_current_object())
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
    if not can_manage_dataset(dataset):
        return jsonify(ok=False, message="没有权限为该数据集构建索引。"), 403

    if dataset.status not in ("processed", "indexed"):
        return jsonify(ok=False, message="数据集需要先完成处理才能构建索引。"), 400

    try:
        metric = request.form.get("metric", "l2")
        if metric not in ("l2", "cosine"):
            raise ValueError("metric 仅支持 l2 或 cosine")
        params = {
            "metric": metric,
            "M": _int_form("M", 16, min_value=2, max_value=128),
            "ef_construction": _int_form("ef_construction", 200, min_value=2, max_value=1000),
            "ef_search": _int_form("ef_search", 100, min_value=1, max_value=1000),
        }
        if params["ef_construction"] < params["M"]:
            raise ValueError("ef_construction 必须大于等于 M")
    except ValueError as e:
        return jsonify(ok=False, message=str(e)), 400

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

    executor.submit(run_build_index_task, task.id, dataset_id, params, current_app._get_current_object())
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
    if task.dataset_id:
        dataset = db.session.get(Dataset, task.dataset_id)
        if dataset and not can_view_dataset(dataset):
            return jsonify(ok=False, message="没有权限查看该任务。"), 403
    return jsonify(ok=True, **_task_to_dict(task))


# ---------------------------------------------------------------------------
# AJAX 检索（同步，直接返回结果）
# ---------------------------------------------------------------------------

@api_bp.route("/search", methods=["POST"])
@login_required
def api_search():
    """AJAX 检索：执行 Top-K 相似细胞检索，返回结果及 Plotly JSON 图数据。"""
    from app.services.search_service import execute_single_search

    try:
        dataset_id = _int_form("dataset_id", 0, min_value=1)
        dataset = db.session.get(Dataset, dataset_id)
        if not dataset:
            return jsonify(ok=False, message="数据集不存在。"), 404
        if not can_view_dataset(dataset):
            return jsonify(ok=False, message="没有权限检索该数据集。"), 403
        raw_index_id = request.form.get("index_id", "").strip()
        if not raw_index_id:
            return jsonify(ok=False, message="请先选择可用索引。"), 400
        index_id = int(raw_index_id)
        query_cell_index = _int_form("query_cell_index", 0, min_value=0)
        top_k = _int_form("top_k", 10, min_value=1, max_value=100)
        filter_cell_type = request.form.get("filter_cell_type", "").strip() or None

        payload = execute_single_search(
            dataset_id=dataset_id,
            index_id=index_id,
            query_cell_index=query_cell_index,
            top_k=top_k,
            filter_cell_type=filter_cell_type,
            max_background_points=15_000,
        )
        return jsonify(ok=True, **payload)
    except ValueError as e:
        return jsonify(ok=False, message=str(e)), 400
    except Exception as e:
        return jsonify(ok=False, message=f"检索失败：{str(e)}"), 500


@api_bp.route("/search/task", methods=["POST"])
@login_required
def api_search_task():
    """提交单数据集检索后台任务，避免同步生成图表阻塞页面。"""
    try:
        dataset_id = _int_form("dataset_id", 0, min_value=1)
        dataset = db.session.get(Dataset, dataset_id)
        if not dataset:
            return jsonify(ok=False, message="数据集不存在。"), 404
        if not can_view_dataset(dataset):
            return jsonify(ok=False, message="没有权限检索该数据集。"), 403
        raw_index_id = request.form.get("index_id", "").strip()
        if not raw_index_id:
            return jsonify(ok=False, message="请先选择可用索引。"), 400
        index_id = int(raw_index_id)
        index = db.session.get(AnnIndex, index_id)
        if not index or index.dataset_id != dataset_id or index.status != "ready":
            return jsonify(ok=False, message="请选择该数据集下可用的 ready 索引。"), 400
        params = {
            "dataset_id": dataset_id,
            "index_id": index_id,
            "query_cell_index": _int_form("query_cell_index", 0, min_value=0),
            "top_k": _int_form("top_k", 10, min_value=1, max_value=100),
            "filter_cell_type": request.form.get("filter_cell_type", "").strip() or None,
            "max_background_points": _int_form("max_background_points", 15_000, min_value=1_000, max_value=50_000),
        }
    except ValueError as e:
        return jsonify(ok=False, message=str(e)), 400

    task = Task(
        type="search",
        status="pending",
        progress=0,
        message="检索任务已提交，等待执行...",
        dataset_id=dataset_id,
        updated_at=datetime.utcnow(),
    )
    db.session.add(task)
    db.session.commit()

    executor.submit(run_search_task, task.id, params, current_app._get_current_object())
    return jsonify(ok=True, task_id=task.id)


# ---------------------------------------------------------------------------
# AJAX 跨数据集检索（fan-out 合并）
# ---------------------------------------------------------------------------

@api_bp.route("/search/multi", methods=["POST"])
@login_required
def api_multi_search():
    """跨多个可访问数据集执行 fan-out 检索并合并排序。"""
    from app.services.multi_search_service import search_across_datasets

    try:
        source_dataset_id = _int_form("dataset_id", 0, min_value=1)
        source_dataset = db.session.get(Dataset, source_dataset_id)
        if not source_dataset:
            return jsonify(ok=False, message="源数据集不存在。"), 404
        if not can_view_dataset(source_dataset):
            return jsonify(ok=False, message="没有权限检索该数据集。"), 403

        raw_index_id = request.form.get("index_id", "").strip()
        if not raw_index_id:
            return jsonify(ok=False, message="请先选择源索引。"), 400
        source_index_id = int(raw_index_id)
        query_cell_index = _int_form("query_cell_index", 0, min_value=0)
        top_k = _int_form("top_k", 20, min_value=1, max_value=100)

        scope = request.form.get("target_scope", "all").strip()
        target_dataset_ids = None
        if scope == "selected":
            raw_ids = request.form.getlist("target_dataset_ids")
            target_dataset_ids = []
            for raw_id in raw_ids:
                try:
                    target_dataset_ids.append(int(raw_id))
                except ValueError:
                    raise ValueError("target_dataset_ids 包含非法数据集 ID")
            if not target_dataset_ids:
                raise ValueError("请选择至少一个目标数据集")

        accessible_ids = [
            row.id
            for row in accessible_datasets_query(
                Dataset.query
                .with_entities(Dataset.id)
                .filter(Dataset.status.in_(["processed", "indexed"]))
            ).all()
        ]
        if target_dataset_ids is None:
            target_dataset_ids = accessible_ids
        else:
            allowed = set(accessible_ids)
            target_dataset_ids = [ds_id for ds_id in target_dataset_ids if ds_id in allowed]

        if not target_dataset_ids:
            return jsonify(ok=False, message="没有可用于跨数据集检索的目标数据集。"), 400

        result_data = search_across_datasets(
            source_dataset_id=source_dataset_id,
            source_index_id=source_index_id,
            query_cell_index=query_cell_index,
            top_k=top_k,
            target_dataset_ids=target_dataset_ids,
        )
        return jsonify(ok=True, result_data=result_data)
    except ValueError as e:
        return jsonify(ok=False, message=str(e)), 400
    except Exception as e:
        return jsonify(ok=False, message=f"跨数据集检索失败：{str(e)}"), 500


@api_bp.route("/search/multi/task", methods=["POST"])
@login_required
def api_multi_search_task():
    """提交跨数据集检索后台任务。"""
    try:
        source_dataset_id = _int_form("dataset_id", 0, min_value=1)
        source_dataset = db.session.get(Dataset, source_dataset_id)
        if not source_dataset:
            return jsonify(ok=False, message="源数据集不存在。"), 404
        if not can_view_dataset(source_dataset):
            return jsonify(ok=False, message="没有权限检索该数据集。"), 403

        raw_index_id = request.form.get("index_id", "").strip()
        if not raw_index_id:
            return jsonify(ok=False, message="请先选择源索引。"), 400
        source_index_id = int(raw_index_id)
        source_index = db.session.get(AnnIndex, source_index_id)
        if not source_index or source_index.dataset_id != source_dataset_id or source_index.status != "ready":
            return jsonify(ok=False, message="请选择源数据集下可用的 ready 索引。"), 400

        target_dataset_ids = None
        scope = request.form.get("target_scope", "all").strip()
        if scope == "selected":
            target_dataset_ids = []
            for raw_id in request.form.getlist("target_dataset_ids"):
                try:
                    target_dataset_ids.append(int(raw_id))
                except ValueError:
                    raise ValueError("target_dataset_ids 包含非法数据集 ID")
            if not target_dataset_ids:
                raise ValueError("请选择至少一个目标数据集")

        accessible_ids = [
            row.id
            for row in accessible_datasets_query(
                Dataset.query
                .with_entities(Dataset.id)
                .filter(Dataset.status.in_(["processed", "indexed"]))
            ).all()
        ]
        if target_dataset_ids is None:
            target_dataset_ids = accessible_ids
        else:
            allowed = set(accessible_ids)
            target_dataset_ids = [ds_id for ds_id in target_dataset_ids if ds_id in allowed]
        if not target_dataset_ids:
            return jsonify(ok=False, message="没有可用于跨数据集检索的目标数据集。"), 400

        params = {
            "dataset_id": source_dataset_id,
            "index_id": source_index_id,
            "query_cell_index": _int_form("query_cell_index", 0, min_value=0),
            "top_k": _int_form("top_k", 20, min_value=1, max_value=100),
            "target_dataset_ids": target_dataset_ids,
        }
    except ValueError as e:
        return jsonify(ok=False, message=str(e)), 400

    task = Task(
        type="multi_search",
        status="pending",
        progress=0,
        message="跨数据集检索任务已提交，等待执行...",
        dataset_id=source_dataset_id,
        updated_at=datetime.utcnow(),
    )
    db.session.add(task)
    db.session.commit()

    executor.submit(run_multi_search_task, task.id, params, current_app._get_current_object())
    return jsonify(ok=True, task_id=task.id)


# ---------------------------------------------------------------------------
# AJAX 评估（同步，直接返回结果）
# ---------------------------------------------------------------------------

@api_bp.route("/evaluate", methods=["POST"])
@login_required
def api_evaluate():
    """AJAX 评估：对比 ANN 与精确检索，返回指标及 Plotly JSON 图数据。"""
    from app.services.eval_service import evaluate_index
    from app.services.plot_service import eval_bar_json

    try:
        dataset_id = _int_form("dataset_id", 0, min_value=1)
        dataset = db.session.get(Dataset, dataset_id)
        if not dataset:
            return jsonify(ok=False, message="数据集不存在。"), 404
        if not can_view_dataset(dataset):
            return jsonify(ok=False, message="没有权限评估该数据集。"), 403
        raw_index_id = request.form.get("index_id", "").strip()
        if not raw_index_id:
            return jsonify(ok=False, message="请先选择可用索引。"), 400
        index_id = int(raw_index_id)
        sample_size = _int_form("sample_size", 10, min_value=1, max_value=50)
        top_k = _int_form("eval_top_k", 10, min_value=1, max_value=100)

        metrics = evaluate_index(dataset_id, index_id, sample_size=sample_size, top_k=top_k)
        bar_plot = eval_bar_json(metrics)
        return jsonify(ok=True, metrics=metrics, bar_plot=bar_plot)
    except ValueError as e:
        return jsonify(ok=False, message=str(e)), 400
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
    if not can_view_dataset(dataset):
        return jsonify(ok=False, message="没有权限查看该数据集。"), 403

    indexes = AnnIndex.query.filter_by(dataset_id=dataset_id).all()
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
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        return jsonify(ok=False, message="数据集不存在。"), 404
    if not can_view_dataset(dataset):
        return jsonify(ok=False, message="没有权限查看该数据集。"), 403
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
    if not can_view_dataset(dataset):
        return jsonify(ok=False, message="没有权限查看该数据集。"), 403

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
        accessible_tasks_query(Task.query)
        .filter(Task.status.in_(["pending", "running"]))
        .order_by(Task.updated_at.desc())
        .all()
    )
    return jsonify(ok=True, tasks=[_task_to_dict(t) for t in tasks])


# ---------------------------------------------------------------------------
# 任务列表（支持状态过滤，用于任务中心）
# ---------------------------------------------------------------------------

@api_bp.route("/tasks", methods=["GET"])
@login_required
def api_tasks():
    """返回任务列表，支持状态过滤。"""
    status_filter = request.args.get("status", "all").strip()
    limit = min(int(request.args.get("limit", 20)), 100)

    query = accessible_tasks_query(Task.query).order_by(Task.updated_at.desc())
    if status_filter != "all" and status_filter in ("pending", "running", "success", "error"):
        query = query.filter_by(status=status_filter)

    tasks = query.limit(limit).all()
    return jsonify(ok=True, tasks=[_task_to_dict(t) for t in tasks])


# ---------------------------------------------------------------------------
# 获取单个细胞元信息（检索页索引预览）
# ---------------------------------------------------------------------------

@api_bp.route("/datasets/<int:dataset_id>/cell-meta/<int:cell_index>", methods=["GET"])
@login_required
def api_cell_meta(dataset_id, cell_index):
    """返回指定数据集中某个细胞的元信息，用于检索页输入索引后预览。"""
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        return jsonify(ok=False, message="数据集不存在。"), 404
    if not can_view_dataset(dataset):
        return jsonify(ok=False, message="没有权限查看该数据集。"), 403
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
    datasets = accessible_datasets_query().order_by(Dataset.created_at.desc()).all()
    dataset_ids = [d.id for d in datasets]
    datasets_total = len(datasets)
    datasets_uploaded = sum(1 for d in datasets if d.status == "uploaded")
    datasets_processed = sum(1 for d in datasets if d.status == "processed")
    datasets_indexed = sum(1 for d in datasets if d.status == "indexed")
    indexes_total = AnnIndex.query.filter(
        AnnIndex.status == "ready",
        AnnIndex.dataset_id.in_(dataset_ids) if dataset_ids else False,
    ).count()
    recent_queries = QueryLog.query.count() if is_admin() else QueryLog.query.filter(QueryLog.dataset_id.in_(dataset_ids)).count()

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
        for t in accessible_tasks_query(Task.query).order_by(Task.updated_at.desc()).limit(5).all()
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
