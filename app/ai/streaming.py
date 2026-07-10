"""Replayable database-backed events used by the same-origin SSE endpoint."""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from sqlalchemy import func

from app.extensions import db
from app.models import AiRun, AiStreamEvent


def emit_stream_event(run_id: int, event_type: str, payload: dict | None = None) -> AiStreamEvent:
    sequence = (
        db.session.query(func.max(AiStreamEvent.sequence)).filter_by(run_id=run_id).scalar() or 0
    ) + 1
    event = AiStreamEvent(
        run_id=run_id,
        sequence=sequence,
        event_type=event_type,
        payload_json=json.dumps(payload or {}, ensure_ascii=False, separators=(",", ":")),
    )
    db.session.add(event)
    return event


def event_payload(event: AiStreamEvent) -> dict:
    try:
        payload = json.loads(event.payload_json or "{}")
    except (TypeError, json.JSONDecodeError):
        payload = {}
    return payload if isinstance(payload, dict) else {}


def stream_is_terminal(run: AiRun | None) -> bool:
    if run is None or run.status in {"error", "rejected", "cancelled"}:
        return True
    return run.status == "success" and run.summary_status in {"model", "fallback", "not_started"}


def cleanup_stream_events(retention_hours: int = 24) -> int:
    cutoff = datetime.utcnow() - timedelta(hours=max(1, retention_hours))
    rows = (
        AiStreamEvent.query.join(AiRun)
        .filter(AiStreamEvent.created_at < cutoff)
        .filter(AiRun.status.in_(["success", "error", "rejected", "cancelled"]))
        .all()
    )
    for row in rows:
        db.session.delete(row)
    if rows:
        db.session.commit()
    return len(rows)

