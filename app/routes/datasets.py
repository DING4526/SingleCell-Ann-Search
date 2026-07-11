from flask import Blueprint, redirect, url_for, flash, abort
from flask_login import current_user, login_required
from app.extensions import db
from app.models import Dataset
from app.services.access_service import can_manage_dataset, can_view_dataset
from app.spa import render_spa
from app.services.deletion_service import DeletionConflict, delete_dataset

datasets_bp = Blueprint("datasets", __name__)


@datasets_bp.route("/datasets")
@login_required
def list_datasets():
    """SPA 数据集列表入口。"""
    return render_spa()


@datasets_bp.route("/datasets/<int:dataset_id>")
@login_required
def detail(dataset_id):
    """SPA 数据集详情入口。"""
    dataset = db.session.get(Dataset, dataset_id)
    if not dataset:
        flash("数据集不存在。", "danger")
        return redirect(url_for("datasets.list_datasets"))
    if not can_view_dataset(dataset):
        abort(403)
    return render_spa()


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

    try:
        delete_dataset(dataset, actor=current_user)
        flash("数据集已删除。", "info")
    except DeletionConflict as exc:
        flash(exc.message, "warning")
    except Exception:
        db.session.rollback()
        flash("数据集删除失败，请稍后重试。", "danger")
    return redirect(url_for("datasets.list_datasets"))
