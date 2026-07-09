from flask import Blueprint
from flask_login import login_required
from app.spa import render_spa

search_bp = Blueprint("search", __name__)


@search_bp.route("/search", methods=["GET"])
@login_required
def search():
    """SPA 检索入口。"""
    return render_spa()
