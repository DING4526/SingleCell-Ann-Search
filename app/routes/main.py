import os
import markdown as md
from flask import Blueprint, render_template, abort
from app.models import Dataset, AnnIndex, QueryLog
from app.extensions import db

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    """首页：展示系统概览统计。"""
    dataset_count = Dataset.query.count()
    index_count = AnnIndex.query.filter_by(status="ready").count()
    query_count = QueryLog.query.count()
    return render_template(
        "index.html",
        dataset_count=dataset_count,
        index_count=index_count,
        query_count=query_count,
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
    return render_template("markdown.html", title=title, content=html_content)
