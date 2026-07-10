"""Centralized system-role and dataset-role authorization."""
from sqlalchemy import or_
from flask_login import current_user

from app.models import Dataset, DatasetPermission, Task


ROLE_RANK = {None: 0, "viewer": 1, "editor": 2, "owner": 3, "admin": 4}


def is_admin(user=None) -> bool:
    user = user or current_user
    return bool(
        getattr(user, "is_authenticated", False)
        and getattr(user, "is_enabled", True)
        and getattr(user, "role", None) == "admin"
    )


def dataset_access_filter(user=None):
    """SQL filter for datasets the user can view."""
    user = user or current_user
    if is_admin(user):
        return None
    if not getattr(user, "is_authenticated", False) or not getattr(user, "is_enabled", True):
        return Dataset.id == -1
    granted_ids = DatasetPermission.query.with_entities(DatasetPermission.dataset_id).filter(
        DatasetPermission.user_id == user.id,
        DatasetPermission.level.in_(["viewer", "editor"]),
    )
    return or_(
        Dataset.owner_id == user.id,
        Dataset.visibility == "shared",
        Dataset.id.in_(granted_ids),
    )


def editable_dataset_filter(user=None):
    """SQL filter for datasets the user can modify as Editor or Owner."""
    user = user or current_user
    if is_admin(user):
        return None
    if not getattr(user, "is_authenticated", False) or not getattr(user, "is_enabled", True):
        return Dataset.id == -1
    editor_ids = DatasetPermission.query.with_entities(DatasetPermission.dataset_id).filter(
        DatasetPermission.user_id == user.id,
        DatasetPermission.level == "editor",
    )
    return or_(Dataset.owner_id == user.id, Dataset.id.in_(editor_ids))


def accessible_datasets_query(query=None, user=None):
    query = query or Dataset.query
    access_filter = dataset_access_filter(user)
    return query if access_filter is None else query.filter(access_filter)


def editable_datasets_query(query=None, user=None):
    query = query or Dataset.query
    edit_filter = editable_dataset_filter(user)
    return query if edit_filter is None else query.filter(edit_filter)


def effective_dataset_role(dataset: Dataset, user=None) -> str | None:
    """Return admin/owner/editor/viewer or None for one dataset."""
    user = user or current_user
    if not dataset or not getattr(user, "is_authenticated", False) or not getattr(user, "is_enabled", True):
        return None
    if is_admin(user):
        return "admin"
    if dataset.owner_id == user.id:
        return "owner"
    permission = DatasetPermission.query.filter_by(dataset_id=dataset.id, user_id=user.id).first()
    if permission and permission.level in ("viewer", "editor"):
        return permission.level
    if dataset.visibility == "shared":
        return "viewer"
    return None


def dataset_permission_source(dataset: Dataset, user=None) -> str | None:
    user = user or current_user
    role = effective_dataset_role(dataset, user)
    if role == "admin":
        return "admin"
    if role == "owner":
        return "owner"
    if role in ("viewer", "editor"):
        explicit = DatasetPermission.query.filter_by(dataset_id=dataset.id, user_id=user.id).first()
        return "explicit" if explicit else "shared"
    return None


def has_dataset_role(dataset: Dataset, minimum: str, user=None) -> bool:
    return ROLE_RANK.get(effective_dataset_role(dataset, user), 0) >= ROLE_RANK[minimum]


def can_view_dataset(dataset: Dataset, user=None) -> bool:
    return has_dataset_role(dataset, "viewer", user)


def can_edit_dataset(dataset: Dataset, user=None) -> bool:
    return has_dataset_role(dataset, "editor", user)


def can_manage_dataset(dataset: Dataset, user=None) -> bool:
    """Owner-level management: sharing, ownership transfer, and deletion."""
    return has_dataset_role(dataset, "owner", user)


def accessible_tasks_query(query=None, user=None):
    """Tasks are visible to creator, dataset editors/owners, and admins."""
    query = query or Task.query
    user = user or current_user
    if is_admin(user):
        return query
    editable_ids = editable_datasets_query(Dataset.query.with_entities(Dataset.id), user)
    return query.filter(or_(Task.created_by_id == user.id, Task.dataset_id.in_(editable_ids)))


def can_view_task(task: Task, user=None) -> bool:
    user = user or current_user
    if not task or not getattr(user, "is_authenticated", False):
        return False
    if is_admin(user) or task.created_by_id == user.id:
        return True
    if task.dataset_id:
        dataset = task.dataset if hasattr(task, "dataset") else None
        dataset = dataset or Dataset.query.get(task.dataset_id)
        return can_edit_dataset(dataset, user)
    return False
