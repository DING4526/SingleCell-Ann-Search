"""资源访问控制工具。"""
from sqlalchemy import or_
from flask_login import current_user
from app.models import Dataset, Task


def is_admin(user=None) -> bool:
    user = user or current_user
    return bool(getattr(user, "is_authenticated", False) and getattr(user, "role", None) == "admin")


def dataset_access_filter(user=None):
    """普通用户可见自己的、共享的和历史未归属数据集。"""
    user = user or current_user
    if is_admin(user):
        return None
    return or_(
        Dataset.owner_id == user.id,
        Dataset.visibility == "shared",
        Dataset.owner_id.is_(None),
    )


def accessible_datasets_query(query=None, user=None):
    query = query or Dataset.query
    access_filter = dataset_access_filter(user)
    if access_filter is not None:
        query = query.filter(access_filter)
    return query


def accessible_tasks_query(query=None, user=None):
    query = query or Task.query
    user = user or current_user
    if is_admin(user):
        return query
    accessible_dataset_ids = accessible_datasets_query(Dataset.query.with_entities(Dataset.id), user)
    return query.filter(
        or_(
            Task.dataset_id.is_(None),
            Task.dataset_id.in_(accessible_dataset_ids),
        )
    )


def can_view_dataset(dataset: Dataset, user=None) -> bool:
    user = user or current_user
    if not dataset or not getattr(user, "is_authenticated", False):
        return False
    return (
        is_admin(user)
        or dataset.owner_id == user.id
        or dataset.visibility == "shared"
        or dataset.owner_id is None
    )


def can_manage_dataset(dataset: Dataset, user=None) -> bool:
    user = user or current_user
    if not dataset or not getattr(user, "is_authenticated", False):
        return False
    return is_admin(user) or dataset.owner_id == user.id or dataset.owner_id is None
