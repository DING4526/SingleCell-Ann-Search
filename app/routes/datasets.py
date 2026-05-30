import os
import pathlib
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required
from werkzeug.utils import secure_filename
from app.extensions import db
from app.models import Dataset, AnnIndex, Cell
from app.services.data_service import process_h5ad_dataset
from app.services.ann_service import build_hnsw_index
from app.services.plot_service import dataset_scatter_html

datasets_bp = Blueprint("datasets", __name__)


@datasets_bp.route("/datasets")
@login_required
def list_datasets():
    """数据集列表页。"""
    datasets = Dataset.query.order_by(Dataset.created_at.desc()).all()
    return render_template("datasets.html", datasets=datasets)


@datasets_bp.route("/datasets/upload", methods=["POST"])
@login_required
def upload():
    """上传 .h5ad 文件。"""
    file = request.files.get("file")
    if not file or not file.filename:
        flash("未选择文件。", "danger")
        return redirect(url_for("datasets.list_datasets"))

    if not file.filename.endswith(".h5ad"):
        flash("仅支持 .h5ad 格式的文件。", "danger")
        return redirect(url_for("datasets.list_datasets"))

    filename = secure_filename(file.filename)
    file_path = os.path.join(current_app.config["RAW_DIR"], filename)
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

    flash(f"数据集「{name}」上传成功，请点击「处理数据集」提取向量。", "success")
    return redirect(url_for("datasets.detail", dataset_id=dataset.id))


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

    # 生成散点图
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


@datasets_bp.route("/datasets/<int:dataset_id>/process", methods=["POST"])
@login_required
def process(dataset_id):
    """处理数据集：提取 PCA 向量和细胞元信息。"""
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        flash("数据集不存在。", "danger")
        return redirect(url_for("datasets.list_datasets"))

    try:
        process_h5ad_dataset(dataset_id)
        flash(
            f"处理完成：{dataset.n_cells} 个细胞，{dataset.n_genes} 个基因，"
            f"向量维度 {dataset.vector_dim}。",
            "success",
        )
    except Exception as e:
        flash(f"处理失败：{str(e)}", "danger")

    return redirect(url_for("datasets.detail", dataset_id=dataset_id))


@datasets_bp.route("/datasets/<int:dataset_id>/build-index", methods=["POST"])
@login_required
def build_index(dataset_id):
    """构建 HNSW 索引。"""
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        flash("数据集不存在。", "danger")
        return redirect(url_for("datasets.list_datasets"))

    metric = request.form.get("metric", "l2")
    M = int(request.form.get("M", 16))
    ef_construction = int(request.form.get("ef_construction", 200))
    ef_search = int(request.form.get("ef_search", 100))

    try:
        ann_index = build_hnsw_index(dataset_id, metric=metric, M=M,
                                      ef_construction=ef_construction, ef_search=ef_search)
        flash(
            f"HNSW 索引构建完成（{metric}, M={M}），耗时 {ann_index.build_time_ms:.1f} ms。",
            "success",
        )
    except Exception as e:
        flash(f"索引构建失败：{str(e)}", "danger")

    return redirect(url_for("datasets.detail", dataset_id=dataset_id))


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
