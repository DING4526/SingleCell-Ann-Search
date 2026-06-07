import os
import pathlib
from flask import Blueprint, render_template, redirect, url_for, flash, current_app
from flask_login import login_required
from app.extensions import db
from app.models import Dataset, AnnIndex, Cell
from app.services.plot_service import dataset_scatter_html

datasets_bp = Blueprint("datasets", __name__)


@datasets_bp.route("/datasets")
@login_required
def list_datasets():
    """数据集列表页。"""
    datasets = Dataset.query.order_by(Dataset.created_at.desc()).all()
    return render_template("datasets.html", datasets=datasets)


@datasets_bp.route("/datasets/<int:dataset_id>")
@login_required
def detail(dataset_id):
    """数据集详情页：展示统计信息、索引状态和可视化。"""
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        flash("数据集不存在。", "danger")
        return redirect(url_for("datasets.list_datasets"))

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

    # 生成散点图（使用旧版 HTML 方式，详情页直接嵌入，不需要 AJAX 交互）
    scatter_html = ""
    if dataset.status in ("processed", "indexed"):
        try:
            scatter_html = dataset_scatter_html(dataset_id)
        except Exception as e:
            scatter_html = f"<p class='text-muted'>可视化暂不可用: {e}</p>"

    return render_template(
        "dataset_detail.html",
        dataset=dataset,
        indexes=indexes,
        stats=stats,
        scatter_html=scatter_html,
    )


@datasets_bp.route("/datasets/<int:dataset_id>/delete", methods=["POST"])
@login_required
def delete(dataset_id):
    """删除数据集及其关联的文件和数据库记录。"""
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        flash("数据集不存在。", "danger")
        return redirect(url_for("datasets.list_datasets"))

    # 删除物理文件
    for path_str in [dataset.file_path]:
        if path_str and os.path.exists(path_str):
            os.remove(path_str)

    if dataset.vector_path:
        vec_path = pathlib.Path(current_app.config["CACHE_DIR"]) / dataset.vector_path
        if vec_path.exists():
            os.remove(str(vec_path))

    for idx in AnnIndex.query.filter_by(dataset_id=dataset_id).all():
        idx_path = pathlib.Path(current_app.config["INDEX_DIR"]) / idx.index_path
        if idx_path.exists():
            os.remove(str(idx_path))

    db.session.delete(dataset)
    db.session.commit()

    flash("数据集已删除。", "info")
    return redirect(url_for("datasets.list_datasets"))
