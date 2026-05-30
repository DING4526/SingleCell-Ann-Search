from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required
from app.extensions import db
from app.models import Dataset, AnnIndex, Cell
from app.services.ann_service import search_by_cell_index
from app.services.eval_service import evaluate_index
from app.services.plot_service import search_scatter_html, eval_bar_html

search_bp = Blueprint("search", __name__)


@search_bp.route("/search", methods=["GET", "POST"])
@login_required
def search():
    """检索页面：选择数据集和索引，执行 Top-K 相似细胞检索。"""
    # 获取已有索引的数据集
    indexed_datasets = (
        Dataset.query.filter(Dataset.status.in_(["processed", "indexed"]))
        .order_by(Dataset.name)
        .all()
    )

    result_data = None
    scatter_html = ""
    selected_dataset_id = None
    selected_index_id = None

    if request.method == "POST":
        selected_dataset_id = int(request.form.get("dataset_id", 0))
        selected_index_id = int(request.form.get("index_id", 0))
        query_cell_index = int(request.form.get("query_cell_index", 0))
        top_k = int(request.form.get("top_k", 10))
        filter_cell_type = request.form.get("filter_cell_type", "").strip() or None

        try:
            result_data = search_by_cell_index(
                dataset_id=selected_dataset_id,
                index_id=selected_index_id,
                query_cell_index=query_cell_index,
                top_k=top_k,
                filter_cell_type=filter_cell_type,
            )

            result_cell_indices = [r["cell_index"] for r in result_data["results"]]
            scatter_html = search_scatter_html(
                selected_dataset_id, query_cell_index, result_cell_indices
            )
        except Exception as e:
            flash(f"检索失败：{str(e)}", "danger")

    # 为每个数据集构建索引选项
    index_options = {}
    for ds in indexed_datasets:
        indexes = AnnIndex.query.filter_by(dataset_id=ds.id, status="ready").all()
        index_options[ds.id] = indexes

    # 获取当前数据集的 cell_type 选项
    cell_types = []
    target_ds = selected_dataset_id or (indexed_datasets[0].id if indexed_datasets else None)
    if target_ds:
        types = (
            db.session.query(Cell.cell_type)
            .filter(Cell.dataset_id == target_ds, Cell.cell_type.isnot(None))
            .distinct()
            .all()
        )
        cell_types = sorted(set(t[0] for t in types if t[0]))

    return render_template(
        "search.html",
        datasets=indexed_datasets,
        index_options=index_options,
        result_data=result_data,
        scatter_html=scatter_html,
        selected_dataset_id=selected_dataset_id,
        selected_index_id=selected_index_id,
        cell_types=cell_types,
    )


@search_bp.route("/evaluate", methods=["POST"])
@login_required
def evaluate():
    """性能评估：对比 ANN 检索和精确检索的召回率和耗时。"""
    dataset_id = int(request.form.get("dataset_id", 0))
    index_id = int(request.form.get("index_id", 0))
    sample_size = int(request.form.get("sample_size", 10))
    top_k = int(request.form.get("eval_top_k", 10))

    try:
        metrics = evaluate_index(dataset_id, index_id, sample_size=sample_size, top_k=top_k)
        bar_html = eval_bar_html(metrics)
        flash(
            f"评估完成：Recall@{top_k}={metrics['avg_recall_at_k']:.2%}，"
            f"加速比={metrics['speedup']:.1f}x",
            "success",
        )
    except Exception as e:
        metrics = None
        bar_html = ""
        flash(f"评估失败：{str(e)}", "danger")

    # 重新渲染检索页面并附带评估结果
    indexed_datasets = (
        Dataset.query.filter(Dataset.status.in_(["processed", "indexed"]))
        .order_by(Dataset.name)
        .all()
    )
    index_options = {}
    for ds in indexed_datasets:
        indexes = AnnIndex.query.filter_by(dataset_id=ds.id, status="ready").all()
        index_options[ds.id] = indexes

    cell_types = []
    if dataset_id:
        types = (
            db.session.query(Cell.cell_type)
            .filter(Cell.dataset_id == dataset_id, Cell.cell_type.isnot(None))
            .distinct()
            .all()
        )
        cell_types = sorted(set(t[0] for t in types if t[0]))

    return render_template(
        "search.html",
        datasets=indexed_datasets,
        index_options=index_options,
        result_data=None,
        scatter_html="",
        selected_dataset_id=dataset_id,
        selected_index_id=index_id,
        cell_types=cell_types,
        eval_metrics=metrics,
        eval_bar_html=bar_html,
    )
