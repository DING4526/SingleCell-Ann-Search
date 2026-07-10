"""API 蓝图：提供 JSON 格式的 AJAX 接口，用于非阻塞操作。"""
import json
import os
import uuid
import pathlib
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user, login_user, logout_user
from werkzeug.utils import secure_filename
from app.extensions import db
from app.models import Dataset, AnnIndex, Cell, Task, QueryLog, User, JointIndex, IndexExperiment, IndexExperimentRun, IndexEvaluation
from app.tasks import (
    executor,
    plot_executor,
    run_process_task,
    run_build_index_task,
    run_search_task,
    run_search_plot_task,
    run_multi_search_task,
    run_index_experiment_task,
    run_index_evaluation_task,
    run_build_joint_index_task,
    run_joint_search_task,
    run_joint_search_plot_task,
)
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

def _task_to_dict(task: Task, include_result: bool = False) -> dict:
    """将 Task 对象序列化为字典。"""
    import json
    result = None
    if include_result and task.result_json:
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
        "has_result": bool(task.result_json),
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


def _optional_int_form(name: str, default=None, min_value: int = None, max_value: int = None):
    if name not in request.form or request.form.get(name) in ("", None):
        return default
    return _int_form(name, default if default is not None else 0, min_value=min_value, max_value=max_value)


def _index_to_dict(idx: AnnIndex) -> dict:
    try:
        params = json.loads(idx.params_json) if idx.params_json else {}
    except Exception:
        params = {}
    source_run = None
    if idx.source_run:
        try:
            source_params = json.loads(idx.source_run.params_json) if idx.source_run.params_json else {}
        except Exception:
            source_params = {}
        source_run = {
            "id": idx.source_run.id,
            "experiment_id": idx.source_run.experiment_id,
            "name": idx.source_run.name,
            "algorithm": idx.source_run.algorithm,
            "params": source_params,
            "status": idx.source_run.status,
            "recall_at_k": idx.source_run.recall_at_k,
            "avg_query_time_ms": idx.source_run.avg_query_time_ms,
            "p95_query_time_ms": idx.source_run.p95_query_time_ms,
            "avg_exact_time_ms": idx.source_run.avg_exact_time_ms,
            "speedup": idx.source_run.speedup,
            "build_time_ms": idx.source_run.build_time_ms,
            "index_size_bytes": idx.source_run.index_size_bytes,
            "quality": idx.source_run.quality,
            "recommendation": idx.source_run.recommendation,
        }
    return {
        "id": idx.id,
        "dataset_id": idx.dataset_id,
        "algorithm": idx.algorithm or "hnswlib_hnsw",
        "params": params,
        "source_experiment_id": idx.source_experiment_id,
        "source_run_id": idx.source_run_id,
        "source_run": source_run,
        "metric": idx.metric,
        "M": idx.M,
        "ef_construction": idx.ef_construction,
        "ef_search": idx.ef_search,
        "build_time_ms": idx.build_time_ms,
        "index_size_bytes": idx.index_size_bytes,
        "backend_version": idx.backend_version,
        "lifecycle": idx.lifecycle or "active",
        "selection_labels": [item for item in (idx.selection_labels or "").split(",") if item],
        "discarded_at": idx.discarded_at.isoformat() if idx.discarded_at else None,
        "status": idx.status,
        "error_message": idx.error_message,
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
        active_indexes = [idx for idx in dataset.indexes if (idx.lifecycle or "active") == "active"]
        data["indexes"] = [_index_to_dict(idx) for idx in active_indexes]
        data["ready_index_count"] = sum(1 for idx in active_indexes if idx.status == "ready")
    return data


def _can_view_joint_index(joint_index: JointIndex) -> bool:
    if not joint_index:
        return False
    included_rows = [row for row in joint_index.datasets if row.status == "included"]
    if not included_rows:
        return is_admin() or joint_index.owner_id == current_user.id
    return all(row.dataset and can_view_dataset(row.dataset) for row in included_rows)


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
        if idx.index_path:
            idx_path = pathlib.Path(current_app.config["INDEX_DIR"]) / idx.index_path
            if idx_path.exists():
                os.remove(str(idx_path))
        if idx.preprocess_path:
            prep_path = pathlib.Path(current_app.config["INDEX_DIR"]) / idx.preprocess_path
            if prep_path.exists():
                os.remove(str(prep_path))


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

@api_bp.route("/ann/algorithms", methods=["GET"])
@login_required
def api_ann_algorithms():
    """Return ANN algorithm backend availability and defaults."""
    from app.services.ann_backend_service import algorithm_catalog

    dataset_id = request.args.get("dataset_id", "").strip()
    n_cells = None
    dim = None
    if dataset_id:
        dataset = db.session.get(Dataset, int(dataset_id))
        if not dataset:
            return jsonify(ok=False, message="Dataset does not exist."), 404
        if not can_view_dataset(dataset):
            return jsonify(ok=False, message="No permission to view this dataset."), 403
        n_cells = dataset.n_cells
        dim = dataset.vector_dim
    return jsonify(ok=True, algorithms=algorithm_catalog(n_cells=n_cells, dim=dim))


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

    try:
        algorithm = request.form.get("algorithm", "hnswlib_hnsw").strip() or "hnswlib_hnsw"
        from app.services.ann_backend_service import algorithm_catalog
        catalog = {item["key"]: item for item in algorithm_catalog(n_cells=dataset.n_cells, dim=dataset.vector_dim)}
        if algorithm not in catalog:
            raise ValueError(f"不支持的 ANN 算法：{algorithm}")
        if not catalog[algorithm].get("available"):
            raise ValueError(catalog[algorithm].get("disabled_reason") or f"算法 {algorithm} 当前不可用")

        backend_params = {key: value for key, value in params.items() if key != "metric" and value is not None}
        raw_params_json = request.form.get("params_json", "").strip()
        if raw_params_json:
            try:
                parsed = json.loads(raw_params_json)
                if isinstance(parsed, dict):
                    backend_params.update(parsed)
            except json.JSONDecodeError:
                raise ValueError("params_json 必须是有效 JSON")
        for key, min_value, max_value in [
            ("projection_dim", 1, 10000),
            ("random_state", None, None),
            ("nlist", 1, 1000000),
            ("nprobe", 1, 1000000),
            ("pq_m", 1, 4096),
            ("nbits", 2, 8),
        ]:
            value = _optional_int_form(key, None, min_value=min_value, max_value=max_value)
            if value is not None:
                backend_params[key] = value
        source_experiment_id = _optional_int_form("source_experiment_id", None, min_value=1)
        source_run_id = _optional_int_form("source_run_id", None, min_value=1)
        if source_run_id:
            source_run = db.session.get(IndexExperimentRun, source_run_id)
            if not source_run or not source_run.experiment:
                raise ValueError("来源基础评估候选不存在")
            if source_run.status != "success":
                raise ValueError("只能从成功的基础评估候选构建真实索引")
            if source_run.experiment.dataset_id != dataset_id:
                raise ValueError("来源基础评估候选不属于当前数据集")
            if source_experiment_id and source_experiment_id != source_run.experiment_id:
                raise ValueError("source_experiment_id 与 source_run_id 不匹配")
            source_experiment_id = source_run.experiment_id
        elif source_experiment_id:
            source_experiment = db.session.get(IndexExperiment, source_experiment_id)
            if not source_experiment or source_experiment.dataset_id != dataset_id:
                raise ValueError("来源基础评估不属于当前数据集")
        params = {
            "algorithm": algorithm,
            "metric": params["metric"],
            "params": backend_params,
            "M": backend_params.get("M"),
            "ef_construction": backend_params.get("ef_construction"),
            "ef_search": backend_params.get("ef_search"),
            "source_experiment_id": source_experiment_id,
            "source_run_id": source_run_id,
        }
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
# 联合索引（Harmony 对齐 + 物理 HNSW）
# ---------------------------------------------------------------------------

@api_bp.route("/joint-indexes", methods=["GET"])
@login_required
def api_joint_indexes():
    """返回当前用户可见的联合索引列表。"""
    from app.services.joint_index_service import joint_index_to_dict

    rows = JointIndex.query.order_by(JointIndex.created_at.desc()).all()
    visible = [row for row in rows if _can_view_joint_index(row)]
    return jsonify(ok=True, joint_indexes=[joint_index_to_dict(row) for row in visible])


@api_bp.route("/joint-indexes/<int:joint_index_id>", methods=["GET"])
@login_required
def api_joint_index_detail(joint_index_id):
    """返回单个联合索引详情。"""
    from app.services.joint_index_service import joint_index_to_dict

    joint_index = db.session.get(JointIndex, joint_index_id)
    if not joint_index:
        return jsonify(ok=False, message="联合索引不存在。"), 404
    if not _can_view_joint_index(joint_index):
        return jsonify(ok=False, message="没有权限查看该联合索引。"), 403
    return jsonify(ok=True, joint_index=joint_index_to_dict(joint_index))


@api_bp.route("/joint-indexes/build/task", methods=["POST"])
@login_required
def api_build_joint_index_task():
    """提交联合索引构建后台任务。"""
    try:
        raw_ids = request.form.getlist("dataset_ids")
        if len(raw_ids) == 1 and "," in raw_ids[0]:
            raw_ids = [item for item in raw_ids[0].split(",") if item.strip()]
        dataset_ids = []
        for raw_id in raw_ids:
            try:
                dataset_ids.append(int(raw_id))
            except ValueError:
                raise ValueError("dataset_ids 包含非法数据集 ID")
        if len(set(dataset_ids)) < 2:
            raise ValueError("联合索引至少需要选择两个数据集")

        datasets = Dataset.query.filter(Dataset.id.in_(dataset_ids)).all()
        dataset_by_id = {dataset.id: dataset for dataset in datasets}
        if len(dataset_by_id) != len(set(dataset_ids)):
            raise ValueError("部分数据集不存在")
        for dataset_id in set(dataset_ids):
            dataset = dataset_by_id[dataset_id]
            if not can_view_dataset(dataset):
                return jsonify(ok=False, message="没有权限使用部分数据集构建联合索引。"), 403
            if dataset.status not in ("processed", "indexed"):
                raise ValueError(f"数据集 {dataset.name} 尚未完成处理")

        metric = request.form.get("metric", "l2").strip()
        if metric not in ("l2", "cosine"):
            raise ValueError("metric 仅支持 l2 或 cosine")
        params = {
            "name": request.form.get("name", "").strip() or "联合索引",
            "dataset_ids": dataset_ids,
            "metric": metric,
            "M": _int_form("M", 16, min_value=2, max_value=128),
            "ef_construction": _int_form("ef_construction", 200, min_value=2, max_value=1000),
            "ef_search": _int_form("ef_search", 100, min_value=1, max_value=1000),
            "n_pcs": _int_form("n_pcs", 50, min_value=2, max_value=200),
            "n_top_genes": _int_form("n_top_genes", 2000, min_value=50, max_value=10000),
            "min_common_genes": _int_form("min_common_genes", 500, min_value=1, max_value=50000),
            "owner_id": current_user.id,
        }
        if params["ef_construction"] < params["M"]:
            raise ValueError("ef_construction 必须大于等于 M")
    except ValueError as e:
        return jsonify(ok=False, message=str(e)), 400

    task = Task(
        type="build_joint_index",
        status="pending",
        progress=0,
        message="联合索引构建任务已提交，等待执行...",
        dataset_id=None,
        updated_at=datetime.utcnow(),
    )
    db.session.add(task)
    db.session.commit()

    executor.submit(run_build_joint_index_task, task.id, params, current_app._get_current_object())
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
    return jsonify(ok=True, **_task_to_dict(task, include_result=True))


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
            max_background_points=8_000,
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
        if not index or index.dataset_id != dataset_id or index.status != "ready" or index.lifecycle != "active":
            return jsonify(ok=False, message="请选择该数据集下可用的 ready 索引。"), 400
        params = {
            "dataset_id": dataset_id,
            "index_id": index_id,
            "query_cell_index": _int_form("query_cell_index", 0, min_value=0),
            "top_k": _int_form("top_k", 10, min_value=1, max_value=100),
            "filter_cell_type": request.form.get("filter_cell_type", "").strip() or None,
            "max_background_points": _int_form("max_background_points", 8_000, min_value=1_000, max_value=50_000),
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


@api_bp.route("/search/plot/task", methods=["POST"])
@login_required
def api_search_plot_task():
    """提交单数据集检索高亮图生成任务，独立于检索结果表格。"""
    try:
        dataset_id = _int_form("dataset_id", 0, min_value=1)
        dataset = db.session.get(Dataset, dataset_id)
        if not dataset:
            return jsonify(ok=False, message="数据集不存在。"), 404
        if not can_view_dataset(dataset):
            return jsonify(ok=False, message="没有权限查看该数据集图表。"), 403

        raw_indices = request.form.getlist("result_cell_indices")
        if len(raw_indices) == 1 and "," in raw_indices[0]:
            raw_indices = [item for item in raw_indices[0].split(",") if item.strip()]
        result_cell_indices = []
        for raw_index in raw_indices:
            try:
                result_cell_indices.append(int(raw_index))
            except ValueError:
                raise ValueError("result_cell_indices 包含非法细胞编号")
        if len(result_cell_indices) > 100:
            raise ValueError("result_cell_indices 最多支持 100 个细胞")

        params = {
            "dataset_id": dataset_id,
            "query_cell_index": _int_form("query_cell_index", 0, min_value=0),
            "result_cell_indices": result_cell_indices,
            "max_background_points": _int_form("max_background_points", 8_000, min_value=1_000, max_value=50_000),
        }
    except ValueError as e:
        return jsonify(ok=False, message=str(e)), 400

    task = Task(
        type="search_plot",
        status="pending",
        progress=0,
        message="检索高亮图任务已提交，等待执行...",
        dataset_id=dataset_id,
        updated_at=datetime.utcnow(),
    )
    db.session.add(task)
    db.session.commit()

    plot_executor.submit(run_search_plot_task, task.id, params, current_app._get_current_object())
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
        if not source_index or source_index.dataset_id != source_dataset_id or source_index.status != "ready" or source_index.lifecycle != "active":
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
# AJAX 联合索引检索
# ---------------------------------------------------------------------------

@api_bp.route("/search/joint/task", methods=["POST"])
@login_required
def api_joint_search_task():
    """提交物理联合索引检索后台任务。"""
    try:
        joint_index_id = _int_form("joint_index_id", 0, min_value=1)
        joint_index = db.session.get(JointIndex, joint_index_id)
        if not joint_index:
            return jsonify(ok=False, message="联合索引不存在。"), 404
        if not _can_view_joint_index(joint_index):
            return jsonify(ok=False, message="没有权限检索该联合索引。"), 403
        if joint_index.status != "ready":
            return jsonify(ok=False, message="联合索引尚未就绪。"), 400

        query_dataset_id = _int_form("query_dataset_id", 0, min_value=1)
        query_dataset = db.session.get(Dataset, query_dataset_id)
        if not query_dataset:
            return jsonify(ok=False, message="查询数据集不存在。"), 404
        if not can_view_dataset(query_dataset):
            return jsonify(ok=False, message="没有权限检索该查询数据集。"), 403

        included_ids = {row.dataset_id for row in joint_index.datasets if row.status == "included"}
        if query_dataset_id not in included_ids:
            raise ValueError("查询数据集未纳入该联合索引")

        params = {
            "joint_index_id": joint_index_id,
            "query_dataset_id": query_dataset_id,
            "query_cell_index": _int_form("query_cell_index", 0, min_value=0),
            "top_k": _int_form("top_k", 20, min_value=1, max_value=100),
        }
    except ValueError as e:
        return jsonify(ok=False, message=str(e)), 400

    task = Task(
        type="joint_search",
        status="pending",
        progress=0,
        message="联合检索任务已提交，等待执行...",
        dataset_id=query_dataset_id,
        updated_at=datetime.utcnow(),
    )
    db.session.add(task)
    db.session.commit()

    executor.submit(run_joint_search_task, task.id, params, current_app._get_current_object())
    return jsonify(ok=True, task_id=task.id)


@api_bp.route("/search/joint/plot/task", methods=["POST"])
@login_required
def api_joint_search_plot_task():
    """提交联合索引高亮图生成任务。"""
    try:
        joint_index_id = _int_form("joint_index_id", 0, min_value=1)
        joint_index = db.session.get(JointIndex, joint_index_id)
        if not joint_index:
            return jsonify(ok=False, message="联合索引不存在。"), 404
        if not _can_view_joint_index(joint_index):
            return jsonify(ok=False, message="没有权限查看该联合索引图表。"), 403
        if joint_index.status != "ready":
            return jsonify(ok=False, message="联合索引尚未就绪。"), 400

        raw_labels = request.form.getlist("result_global_labels")
        if len(raw_labels) == 1 and "," in raw_labels[0]:
            raw_labels = [item for item in raw_labels[0].split(",") if item.strip()]
        result_global_labels = []
        for raw_label in raw_labels:
            try:
                result_global_labels.append(int(raw_label))
            except ValueError:
                raise ValueError("result_global_labels 包含非法 global label")
        if len(result_global_labels) > 200:
            raise ValueError("result_global_labels 最多支持 200 个细胞")

        params = {
            "joint_index_id": joint_index_id,
            "query_global_label": _int_form("query_global_label", 0, min_value=0),
            "result_global_labels": result_global_labels,
            "max_background_points": _int_form("max_background_points", 12_000, min_value=1_000, max_value=50_000),
        }
    except ValueError as e:
        return jsonify(ok=False, message=str(e)), 400

    task = Task(
        type="joint_search_plot",
        status="pending",
        progress=0,
        message="联合高亮图任务已提交，等待执行...",
        dataset_id=None,
        updated_at=datetime.utcnow(),
    )
    db.session.add(task)
    db.session.commit()

    plot_executor.submit(run_joint_search_plot_task, task.id, params, current_app._get_current_object())
    return jsonify(ok=True, task_id=task.id)


# ---------------------------------------------------------------------------
# AJAX 评估（同步，直接返回结果）
# ---------------------------------------------------------------------------

@api_bp.route("/index-experiments", methods=["GET"])
@login_required
def api_index_experiments():
    """List ANN algorithm experiments visible to the current user."""
    from app.services.index_experiment_service import experiment_to_dict

    dataset_id = request.args.get("dataset_id", "").strip()
    query = IndexExperiment.query.join(Dataset, Dataset.id == IndexExperiment.dataset_id)
    visible_dataset_ids = [
        row.id
        for row in accessible_datasets_query(Dataset.query.with_entities(Dataset.id)).all()
    ]
    if not visible_dataset_ids:
        return jsonify(ok=True, experiments=[])
    query = query.filter(IndexExperiment.dataset_id.in_(visible_dataset_ids))
    if dataset_id:
        query = query.filter(IndexExperiment.dataset_id == int(dataset_id))
    rows = query.order_by(IndexExperiment.created_at.desc()).limit(50).all()
    return jsonify(ok=True, experiments=[experiment_to_dict(row, include_runs=False) for row in rows])


@api_bp.route("/index-experiments/<int:experiment_id>", methods=["GET"])
@login_required
def api_index_experiment_detail(experiment_id):
    """Return one ANN algorithm experiment with run metrics."""
    from app.services.index_experiment_service import experiment_to_dict

    experiment = db.session.get(IndexExperiment, experiment_id)
    if not experiment:
        return jsonify(ok=False, message="Experiment does not exist."), 404
    if not experiment.dataset or not can_view_dataset(experiment.dataset):
        return jsonify(ok=False, message="No permission to view this experiment."), 403
    return jsonify(ok=True, experiment=experiment_to_dict(experiment))


@api_bp.route("/index-experiments/task", methods=["POST"])
@login_required
def api_index_experiment_task():
    """Create a persistent candidate experiment and submit its build/evaluation task."""
    from app.services.index_experiment_service import ExperimentConflict, create_index_experiment

    try:
        dataset_id = _int_form("dataset_id", 0, min_value=1)
        dataset = db.session.get(Dataset, dataset_id)
        if not dataset:
            return jsonify(ok=False, message="Dataset does not exist."), 404
        if not can_manage_dataset(dataset):
            return jsonify(ok=False, message="没有权限为该数据集构建候选索引。"), 403
        if dataset.status not in ("processed", "indexed"):
            return jsonify(ok=False, message="Dataset must be processed first."), 400
        metric = request.form.get("metric", "l2").strip()
        if metric not in ("l2", "cosine"):
            raise ValueError("metric must be l2 or cosine")
        candidate_keys = request.form.getlist("candidate_keys")
        if len(candidate_keys) == 1 and "," in candidate_keys[0]:
            candidate_keys = [item for item in candidate_keys[0].split(",") if item.strip()]
        candidate_configs = None
        raw_candidate_configs = request.form.get("candidate_configs", "").strip()
        if raw_candidate_configs:
            candidate_configs = json.loads(raw_candidate_configs)
            if not isinstance(candidate_configs, list):
                raise ValueError("candidate_configs 必须是 JSON 数组")
        experiment = create_index_experiment(
            dataset_id=dataset_id,
            metric=metric,
            sample_size=_int_form("sample_size", 100, min_value=1, max_value=200),
            top_k=_int_form("top_k", 10, min_value=1, max_value=100),
            seed=_int_form("seed", 42, min_value=0, max_value=2_147_483_647),
            repetitions=_int_form("repetitions", 3, min_value=1, max_value=10),
            warmup_count=_int_form("warmup_count", 10, min_value=0, max_value=200),
            candidate_configs=candidate_configs,
            candidate_keys=candidate_keys or None,
        )
        params = {"dataset_id": dataset_id, "experiment_id": experiment.id}
    except ExperimentConflict as e:
        return jsonify(ok=False, message=str(e)), 409
    except json.JSONDecodeError:
        return jsonify(ok=False, message="candidate_configs 不是有效 JSON"), 400
    except ValueError as e:
        return jsonify(ok=False, message=str(e)), 400

    task = Task(
        type="index_experiment",
        status="pending",
        progress=0,
        message="候选索引实验已提交，等待执行...",
        dataset_id=dataset_id,
        updated_at=datetime.utcnow(),
    )
    db.session.add(task)
    db.session.commit()

    executor.submit(run_index_experiment_task, task.id, params, current_app._get_current_object())
    return jsonify(ok=True, task_id=task.id, experiment_id=experiment.id)


@api_bp.route("/index-experiments/<int:experiment_id>/finalize", methods=["POST"])
@login_required
def api_finalize_index_experiment(experiment_id):
    from app.services.index_experiment_service import ExperimentConflict, finalize_experiment

    experiment = db.session.get(IndexExperiment, experiment_id)
    if not experiment:
        return jsonify(ok=False, message="实验不存在。"), 404
    if not experiment.dataset or not can_manage_dataset(experiment.dataset):
        return jsonify(ok=False, message="没有权限完成该实验的选优。"), 403
    try:
        raw_ids = request.form.getlist("selected_run_ids")
        if len(raw_ids) == 1 and "," in raw_ids[0]:
            raw_ids = [item for item in raw_ids[0].split(",") if item.strip()]
        result = finalize_experiment(experiment_id, [int(value) for value in raw_ids])
        return jsonify(ok=True, finalization=result, message="索引保留集合已更新。")
    except ExperimentConflict as exc:
        return jsonify(ok=False, message=str(exc)), 409
    except (TypeError, ValueError) as exc:
        return jsonify(ok=False, message=str(exc)), 400


@api_bp.route("/index-experiments/<int:experiment_id>/discard", methods=["POST"])
@login_required
def api_discard_index_experiment(experiment_id):
    from app.services.index_experiment_service import ExperimentConflict, discard_experiment

    experiment = db.session.get(IndexExperiment, experiment_id)
    if not experiment:
        return jsonify(ok=False, message="实验不存在。"), 404
    if not experiment.dataset or not can_manage_dataset(experiment.dataset):
        return jsonify(ok=False, message="没有权限放弃该实验。"), 403
    try:
        return jsonify(ok=True, cleanup=discard_experiment(experiment_id), message="实验已放弃，候选文件已清理。")
    except ExperimentConflict as exc:
        return jsonify(ok=False, message=str(exc)), 409


@api_bp.route("/index-experiments/<int:experiment_id>/cleanup", methods=["POST"])
@login_required
def api_cleanup_index_experiment(experiment_id):
    from app.services.index_experiment_service import retry_experiment_cleanup

    experiment = db.session.get(IndexExperiment, experiment_id)
    if not experiment:
        return jsonify(ok=False, message="实验不存在。"), 404
    if not experiment.dataset or not can_manage_dataset(experiment.dataset):
        return jsonify(ok=False, message="没有权限清理该实验。"), 403
    return jsonify(ok=True, cleanup=retry_experiment_cleanup(experiment_id), message="清理重试完成。")


@api_bp.route("/index-evaluations", methods=["GET"])
@login_required
def api_index_evaluations():
    """List persisted index evaluations visible to the current user."""
    from app.services.index_evaluation_service import index_evaluation_to_dict

    visible_dataset_ids = [
        row.id
        for row in accessible_datasets_query(Dataset.query.with_entities(Dataset.id)).all()
    ]
    if not visible_dataset_ids:
        return jsonify(ok=True, evaluations=[])

    query = IndexEvaluation.query.filter(IndexEvaluation.dataset_id.in_(visible_dataset_ids))
    dataset_id = request.args.get("dataset_id", "").strip()
    index_id = request.args.get("index_id", "").strip()
    try:
        if dataset_id:
            dataset_id_int = int(dataset_id)
            dataset = db.session.get(Dataset, dataset_id_int)
            if not dataset:
                return jsonify(ok=False, message="Dataset does not exist."), 404
            if not can_view_dataset(dataset):
                return jsonify(ok=False, message="No permission to view this dataset."), 403
            query = query.filter(IndexEvaluation.dataset_id == dataset_id_int)
        if index_id:
            index_id_int = int(index_id)
            ann_index = db.session.get(AnnIndex, index_id_int)
            if not ann_index:
                return jsonify(ok=False, message="Index does not exist."), 404
            if not ann_index.dataset or not can_view_dataset(ann_index.dataset):
                return jsonify(ok=False, message="No permission to view this index."), 403
            query = query.filter(IndexEvaluation.index_id == index_id_int)
    except ValueError:
        return jsonify(ok=False, message="dataset_id and index_id must be integers."), 400

    rows = query.order_by(IndexEvaluation.created_at.desc()).limit(80).all()
    return jsonify(ok=True, evaluations=[index_evaluation_to_dict(row) for row in rows])


@api_bp.route("/index-evaluations/<int:evaluation_id>", methods=["GET"])
@login_required
def api_index_evaluation_detail(evaluation_id):
    """Return one persisted index evaluation."""
    from app.services.index_evaluation_service import index_evaluation_to_dict

    evaluation = db.session.get(IndexEvaluation, evaluation_id)
    if not evaluation:
        return jsonify(ok=False, message="Evaluation does not exist."), 404
    if not evaluation.dataset or not can_view_dataset(evaluation.dataset):
        return jsonify(ok=False, message="No permission to view this evaluation."), 403
    return jsonify(ok=True, evaluation=index_evaluation_to_dict(evaluation))


@api_bp.route("/index-evaluations/task", methods=["POST"])
@login_required
def api_index_evaluation_task():
    """Submit an async persisted index evaluation task."""
    try:
        dataset_id = _int_form("dataset_id", 0, min_value=1)
        index_id = _int_form("index_id", 0, min_value=1)
        dataset = db.session.get(Dataset, dataset_id)
        if not dataset:
            return jsonify(ok=False, message="Dataset does not exist."), 404
        if not can_view_dataset(dataset):
            return jsonify(ok=False, message="No permission to evaluate this dataset."), 403
        ann_index = db.session.get(AnnIndex, index_id)
        if not ann_index or ann_index.dataset_id != dataset_id:
            return jsonify(ok=False, message="Please choose a ready index from this dataset."), 400
        if ann_index.status != "ready":
            return jsonify(ok=False, message="Index is not ready."), 400
        params = {
            "dataset_id": dataset_id,
            "index_id": index_id,
            "sample_size": _int_form("sample_size", 100, min_value=1, max_value=200),
            "top_k": _int_form("top_k", 10, min_value=1, max_value=100),
            "seed": _int_form("seed", 42, min_value=0, max_value=2_147_483_647),
        }
    except ValueError as e:
        return jsonify(ok=False, message=str(e)), 400

    task = Task(
        type="index_evaluation",
        status="pending",
        progress=0,
        message="Index evaluation task submitted.",
        dataset_id=dataset_id,
        updated_at=datetime.utcnow(),
    )
    db.session.add(task)
    db.session.commit()

    executor.submit(run_index_evaluation_task, task.id, params, current_app._get_current_object())
    return jsonify(ok=True, task_id=task.id)


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
        indexes=[_index_to_dict(idx) for idx in indexes],
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
        AnnIndex.lifecycle == "active",
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
