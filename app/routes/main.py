import os
import markdown as md
from flask import Blueprint, render_template, abort
from flask_login import login_required
from app.models import Dataset, AnnIndex, QueryLog, Task
from app.extensions import db
from app.services.access_service import accessible_datasets_query, accessible_tasks_query, is_admin

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
@login_required
def index():
    """工作台首页：展示系统概览、工作流进度与最近活动。"""
    datasets = accessible_datasets_query().order_by(Dataset.created_at.desc()).all()
    dataset_count = len(datasets)
    datasets_by_status = {
        "uploaded": sum(1 for d in datasets if d.status == "uploaded"),
        "processed": sum(1 for d in datasets if d.status == "processed"),
        "indexed": sum(1 for d in datasets if d.status == "indexed"),
        "error": sum(1 for d in datasets if d.status == "error"),
    }
    dataset_ids = [d.id for d in datasets]
    index_count = AnnIndex.query.filter(
        AnnIndex.status == "ready",
        AnnIndex.dataset_id.in_(dataset_ids) if dataset_ids else False,
    ).count()
    query_count = QueryLog.query.count() if is_admin() else QueryLog.query.filter(QueryLog.dataset_id.in_(dataset_ids)).count()

    recent_datasets = datasets[:5]
    recent_tasks = (
        accessible_tasks_query().order_by(Task.updated_at.desc()).limit(5).all()
    )

    first_uploaded_id = next(
        (d.id for d in datasets if d.status == "uploaded"), None
    )
    first_processed_id = next(
        (d.id for d in datasets if d.status == "processed"), None
    )

    return render_template(
        "index.html",
        nav_active="workbench",
        dataset_count=dataset_count,
        datasets_by_status=datasets_by_status,
        index_count=index_count,
        query_count=query_count,
        recent_datasets=recent_datasets,
        recent_tasks=recent_tasks,
        first_uploaded_id=first_uploaded_id,
        first_processed_id=first_processed_id,
    )


@main_bp.route("/background")
def background():
    """项目背景页：读取 background.md 并渲染。"""
    return _render_markdown_page("background.md", "项目背景")


@main_bp.route("/data")
def data_info():
    """数据说明页：读取 data.md 并渲染。"""
    return _render_markdown_page("data.md", "数据说明")


def _render_markdown_page(filename, title):
    """读取项目根目录的 Markdown 文件并转为 HTML 展示。"""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    filepath = os.path.join(base_dir, filename)
    if not os.path.exists(filepath):
        abort(404)
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    html_content = md.markdown(content, extensions=["tables", "fenced_code"])
    return render_template("markdown.html", nav_active="docs", title=title, content=html_content)
