import os
import pathlib
from flask import Blueprint, render_template, redirect, url_for, flash, current_app, abort
from flask_login import login_required
from app.extensions import db
from app.models import Dataset, AnnIndex, Cell, Task
from app.services.access_service import accessible_datasets_query, can_manage_dataset, can_view_dataset

datasets_bp = Blueprint("datasets", __name__)


@datasets_bp.route("/datasets")
@login_required
def list_datasets():
    """数据集列表页。"""
    datasets = accessible_datasets_query().order_by(Dataset.created_at.desc()).all()
    return render_template("datasets.html", nav_active="datasets", datasets=datasets)


@datasets_bp.route("/datasets/<int:dataset_id>")
@login_required
def detail(dataset_id):
    """数据集详情页：展示统计信息、索引状态和可视化（散点图由前端 AJAX 异步加载）。"""
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        flash("数据集不存在。", "danger")
        return redirect(url_for("datasets.list_datasets"))
    if not can_view_dataset(dataset):
        abort(403)

    indexes = AnnIndex.query.filter_by(dataset_id=dataset_id).all()

    # 统计各维度的分布
    stats = {}
    if dataset.status in ("processed", "indexed"):
        for col in ["cell_type", "disease", "age_group"]:
            counts = (
                db.session.query(getattr(Cell, col), db.func.count(Cell.id))
                .filter(Cell.dataset_id == dataset_id)
                .group_by(getattr(Cell, col))
                .order_by(db.func.count(Cell.id).desc())
                .all()
            )
            stats[col] = [(k or "N/A", v) for k, v in counts]

    # 最近 5 条任务
    recent_tasks = (
        Task.query.filter_by(dataset_id=dataset_id)
        .order_by(Task.updated_at.desc())
        .limit(5)
        .all()
    )

    return render_template(
        "dataset_detail.html",
        nav_active="datasets",
        dataset=dataset,
        indexes=indexes,
        stats=stats,
        recent_tasks=recent_tasks,
    )


@datasets_bp.route("/datasets/<int:dataset_id>/delete", methods=["POST"])
@login_required
def delete(dataset_id):
    """删除数据集及其关联的文件和数据库记录。"""
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        flash("数据集不存在。", "danger")
        return redirect(url_for("datasets.list_datasets"))
    if not can_manage_dataset(dataset):
        abort(403)

    # 删除物理文件（仅在该文件不被其他数据集引用时才删除）
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

    db.session.delete(dataset)
    db.session.commit()

    flash("数据集已删除。", "info")
    return redirect(url_for("datasets.list_datasets"))
