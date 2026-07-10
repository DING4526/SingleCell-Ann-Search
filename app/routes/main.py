import os
import markdown as md
from flask import Blueprint, render_template, abort
from flask_login import login_required
from app.models import Dataset, AnnIndex, QueryLog, Task
from app.extensions import db
from app.services.access_service import accessible_datasets_query, accessible_tasks_query, is_admin
from app.spa import render_spa, serve_spa_asset

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
@login_required
def index():
    """SPA entrypoint."""
    return render_spa()


@main_bp.route("/assets/<path:filename>")
def spa_assets(filename):
    """Serve Vite production assets."""
    return serve_spa_asset(filename)


@main_bp.route("/overview")
@main_bp.route("/index-lab")
@main_bp.route("/joint-indexes")
@main_bp.route("/query-lab")
@main_bp.route("/evaluation")
@main_bp.route("/access")
@main_bp.route("/ai-analysis")
@main_bp.route("/ai-knowledge")
@login_required
def spa_pages():
    """Top-level SPA routes."""
    return render_spa()


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
