from flask import Blueprint, redirect
from flask_login import login_required
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
@main_bp.route("/ai-assistant")
@login_required
def spa_pages():
    """Top-level SPA routes."""
    return render_spa()


@main_bp.route("/background")
def background():
    """Retired documentation entry; keep old bookmarks on the product UI."""
    return redirect("/overview")


@main_bp.route("/data")
def data_info():
    """Retired data guide entry; keep old bookmarks on the product UI."""
    return redirect("/overview")
