"""Small, transaction-friendly audit logging helpers."""
import json

from flask import has_request_context, request
from flask_login import current_user

from app.extensions import db
from app.models import AuditLog


def record_audit(
    event: str,
    *,
    actor=None,
    resource_type: str | None = None,
    resource_id: int | None = None,
    dataset_id: int | None = None,
    target_user_id: int | None = None,
    details: dict | None = None,
) -> AuditLog:
    """Add an audit event to the current transaction without committing it."""
    if actor is None and getattr(current_user, "is_authenticated", False):
        actor = current_user
    ip_address = None
    if has_request_context():
        forwarded = request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
        ip_address = forwarded or request.remote_addr
    row = AuditLog(
        actor_id=getattr(actor, "id", None),
        event=event,
        resource_type=resource_type,
        resource_id=resource_id,
        dataset_id=dataset_id,
        target_user_id=target_user_id,
        details_json=json.dumps(details or {}, ensure_ascii=False),
        ip_address=ip_address,
    )
    db.session.add(row)
    return row


def audit_to_dict(row: AuditLog, *, include_ip: bool = False) -> dict:
    try:
        details = json.loads(row.details_json) if row.details_json else {}
    except (TypeError, json.JSONDecodeError):
        details = {}
    return {
        "id": row.id,
        "event": row.event,
        "actor_id": row.actor_id,
        "actor_name": row.actor.username if row.actor else None,
        "resource_type": row.resource_type,
        "resource_id": row.resource_id,
        "dataset_id": row.dataset_id,
        "target_user_id": row.target_user_id,
        "target_user_name": row.target_user.username if row.target_user else None,
        "details": details,
        "ip_address": row.ip_address if include_ip else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
