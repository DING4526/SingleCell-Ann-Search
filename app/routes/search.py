from flask import Blueprint, render_template
from flask_login import login_required
from app.extensions import db
from app.models import Dataset, AnnIndex, Cell

search_bp = Blueprint("search", __name__)


@search_bp.route("/search", methods=["GET"])
@login_required
def search():
    """检索页面：选择数据集和索引，展示检索/评估 UI（内容通过 AJAX 填充）。"""
    indexed_datasets = (
        Dataset.query.filter(Dataset.status.in_(["processed", "indexed"]))
        .order_by(Dataset.name)
        .all()
    )

    index_options = {}
    for ds in indexed_datasets:
        indexes = AnnIndex.query.filter_by(dataset_id=ds.id, status="ready").all()
        index_options[ds.id] = indexes

    # 初始加载第一个数据集的 cell_type 选项
    cell_types = []
    if indexed_datasets:
        types = (
            db.session.query(Cell.cell_type)
            .filter(Cell.dataset_id == indexed_datasets[0].id, Cell.cell_type.isnot(None))
            .distinct()
            .all()
        )
        cell_types = sorted(set(t[0] for t in types if t[0]))

    return render_template(
        "search.html",
        datasets=indexed_datasets,
        index_options=index_options,
        cell_types=cell_types,
        selected_dataset_id=indexed_datasets[0].id if indexed_datasets else None,
        selected_index_id=None,
    )
