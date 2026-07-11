"""Transaction-safe resource deletion and user-facing history removal.

Database rows are committed before any physical artifact is unlinked.  File
cleanup is represented by a persistent ``artifact_cleanup`` task so a failed
unlink is visible and retryable instead of leaving the database half-deleted.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from flask import current_app
from sqlalchemy import or_

from app.extensions import db
from app.models import (
    AiCitation,
    AiConversation,
    AiMessage,
    AiProviderCall,
    AiRun,
    AiStreamEvent,
    AiToolCall,
    AnnIndex,
    AuditLog,
    Cell,
    Dataset,
    DatasetPermission,
    IndexEvaluation,
    IndexExperiment,
    IndexExperimentRun,
    JointIndex,
    JointIndexDataset,
    JointQueryLog,
    KnowledgeChunk,
    KnowledgeDocument,
    QueryLog,
    Task,
)
from app.services.audit_service import record_audit


ACTIVE_TASK_STATUSES = {"pending", "running"}
TERMINAL_TASK_STATUSES = {"success", "error", "cancelled", "canceled"}
ACTIVE_RUN_STATUSES = {
    "queued", "planning", "needs_input", "awaiting_confirmation", "executing", "streaming"
}
MANAGED_ROOTS = ("RAW_DIR", "CACHE_DIR", "INDEX_DIR", "KNOWLEDGE_DIR")


@dataclass
class DeletionConflict(RuntimeError):
    code: str
    message: str
    blockers: list[dict]

    def __str__(self) -> str:
        return self.message


def _blocker(kind: str, object_id: int | None, label: str, **details) -> dict:
    value = {"type": kind, "id": object_id, "label": label}
    value.update(details)
    return value


def conflict_payload(exc: DeletionConflict) -> dict:
    return {
        "ok": False,
        "code": exc.code,
        "error_code": exc.code,
        "message": exc.message,
        "blockers": exc.blockers,
    }


def _json_object(value: str | None) -> dict:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _request_references(value, key: str, object_id: int) -> bool:
    if isinstance(value, dict):
        for next_key, next_value in value.items():
            if next_key == key:
                if isinstance(next_value, list):
                    if any(str(item) == str(object_id) for item in next_value):
                        return True
                elif str(next_value) == str(object_id):
                    return True
            if _request_references(next_value, key, object_id):
                return True
    elif isinstance(value, list):
        return any(_request_references(item, key, object_id) for item in value)
    return False


def _active_tasks_referencing(key: str, object_id: int) -> list[Task]:
    rows = Task.query.filter(Task.status.in_(ACTIVE_TASK_STATUSES)).all()
    return [row for row in rows if _request_references(_json_object(row.request_json), key, object_id)]


def dataset_delete_blockers(dataset: Dataset) -> list[dict]:
    blockers = []
    reference_keys = (
        "dataset_id", "dataset_ids", "target_dataset_ids", "query_dataset_id", "source_dataset_id"
    )
    for task in Task.query.filter(Task.status.in_(ACTIVE_TASK_STATUSES)).all():
        request_data = _json_object(task.request_json)
        if task.dataset_id == dataset.id or any(
            _request_references(request_data, key, dataset.id) for key in reference_keys
        ):
            blockers.append(_blocker(
                "task", task.id, task.message or "数据集仍有进行中的任务", status=task.status
            ))
    for index in AnnIndex.query.filter_by(dataset_id=dataset.id, status="building").all():
        blockers.append(_blocker("ann_index", index.id, "数据集索引仍在构建", status=index.status))
    for experiment in IndexExperiment.query.filter(
        IndexExperiment.dataset_id == dataset.id,
        IndexExperiment.status.in_(["pending", "running"]),
    ).all():
        blockers.append(_blocker(
            "index_experiment", experiment.id, "数据集实验仍在运行", status=experiment.status
        ))
    for evaluation in IndexEvaluation.query.filter(
        IndexEvaluation.dataset_id == dataset.id,
        IndexEvaluation.status.in_(["pending", "running"]),
    ).all():
        blockers.append(_blocker(
            "index_evaluation", evaluation.id, "数据集评估仍在运行", status=evaluation.status
        ))
    for document in KnowledgeDocument.query.filter(
        KnowledgeDocument.dataset_id == dataset.id,
        KnowledgeDocument.status.in_(["pending", "extracting", "indexing"]),
    ).all():
        blockers.append(_blocker(
            "knowledge_document", document.id, "数据集知识资料仍在处理", status=document.status
        ))

    for member in JointIndexDataset.query.filter_by(dataset_id=dataset.id).all():
        joint = db.session.get(JointIndex, member.joint_index_id)
        blockers.append(_blocker(
            "joint_index", member.joint_index_id,
            joint.name if joint else "联合索引",
            status=joint.status if joint else None,
        ))
    return blockers


def ann_index_delete_blockers(index: AnnIndex) -> list[dict]:
    blockers = []
    if index.status == "building":
        blockers.append(_blocker("ann_index", index.id, "索引仍在构建", status=index.status))
    for evaluation in IndexEvaluation.query.filter(
        IndexEvaluation.index_id == index.id,
        IndexEvaluation.status.in_(["pending", "running"]),
    ).all():
        blockers.append(_blocker("index_evaluation", evaluation.id, "索引评估仍在运行", status=evaluation.status))
    if index.source_experiment_id:
        experiment = db.session.get(IndexExperiment, index.source_experiment_id)
        if experiment and experiment.status in {"pending", "running"}:
            blockers.append(_blocker("index_experiment", experiment.id, "候选索引实验仍在运行", status=experiment.status))
    for task in _active_tasks_referencing("index_id", index.id):
        blockers.append(_blocker("task", task.id, task.message or "索引仍被进行中的任务使用", status=task.status))
    return blockers


def joint_index_delete_blockers(joint_index: JointIndex) -> list[dict]:
    blockers = []
    if joint_index.status == "building":
        blockers.append(_blocker("joint_index", joint_index.id, "联合索引仍在构建", status=joint_index.status))
    for task in _active_tasks_referencing("joint_index_id", joint_index.id):
        blockers.append(_blocker("task", task.id, task.message or "联合索引仍被进行中的任务使用", status=task.status))
    return blockers


def document_delete_blockers(document: KnowledgeDocument) -> list[dict]:
    if document.source_type == "builtin":
        return [_blocker("knowledge_document", document.id, "内置知识资料为只读资源")]
    if document.status in {"pending", "extracting", "indexing"}:
        return [_blocker("knowledge_document", document.id, "知识资料仍在处理中", status=document.status)]
    return []


def conversation_delete_blockers(conversation: AiConversation) -> list[dict]:
    blockers = []
    seen_tasks = set()
    for run in conversation.runs:
        if run.status in ACTIVE_RUN_STATUSES or (
            run.status == "success" and run.summary_status in {"pending", "running"}
        ):
            blockers.append(_blocker(
                "ai_run", run.id, "AI 会话仍有进行中的任务", status=run.status
            ))
        linked_tasks = [run.search_task]
        linked_tasks.extend(tool.task for tool in run.tool_calls)
        for task in linked_tasks:
            if task and task.id not in seen_tasks and task.status in ACTIVE_TASK_STATUSES:
                blockers.append(_blocker(
                    "task", task.id, task.message or "AI 会话关联任务仍在运行", status=task.status
                ))
                seen_tasks.add(task.id)
    return blockers


def _managed_artifact(value: str | None, root_key: str) -> dict | None:
    if not value:
        return None
    root = pathlib.Path(current_app.config[root_key]).resolve()
    candidate = pathlib.Path(value)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    if candidate != root and root not in candidate.parents:
        raise DeletionConflict(
            "UNMANAGED_ARTIFACT_PATH",
            "资源包含不受平台管理的文件路径，已停止删除。",
            [_blocker("artifact", None, str(candidate), managed_root=root_key)],
        )
    return {"path": str(candidate), "root": root_key}


def _dedupe_artifacts(items: Iterable[dict | None]) -> list[dict]:
    result = []
    seen = set()
    for item in items:
        if not item or item["path"] in seen:
            continue
        seen.add(item["path"])
        result.append(item)
    return result


def _queue_cleanup(artifacts: list[dict], *, actor_id: int | None, label: str) -> Task | None:
    if not artifacts:
        return None
    task = Task(
        type="artifact_cleanup",
        source="system",
        status="pending",
        progress=0,
        message=f"正在清理{label}的物理文件。",
        request_json=json.dumps({"artifacts": artifacts, "label": label}, ensure_ascii=False),
        created_by_id=actor_id,
        history_hidden=False,
        updated_at=datetime.utcnow(),
    )
    db.session.add(task)
    return task


def process_cleanup_task(task: Task) -> dict:
    if not task or task.type != "artifact_cleanup":
        raise ValueError("清理任务不存在。")
    payload = _json_object(task.request_json)
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), list) else []
    errors = []
    removed = 0
    task.status = "running"
    task.progress = 10
    task.history_hidden = False
    db.session.commit()
    for artifact in artifacts:
        try:
            if not isinstance(artifact, dict) or artifact.get("root") not in MANAGED_ROOTS:
                raise ValueError("清理任务包含无效路径声明")
            checked = _managed_artifact(str(artifact.get("path") or ""), artifact["root"])
            path = pathlib.Path(checked["path"])
            if path.is_file():
                path.unlink()
                removed += 1
            elif path.exists():
                raise OSError("目标不是普通文件")
        except Exception as exc:  # keep the retry task durable and user-visible
            errors.append({"path": str(artifact.get("path") if isinstance(artifact, dict) else artifact), "error": str(exc)[:300]})
    task.progress = 100
    task.updated_at = datetime.utcnow()
    if errors:
        task.status = "error"
        task.error_message = json.dumps(errors, ensure_ascii=False)
        task.message = "部分物理文件清理失败，可重试此清理任务。"
        task.history_hidden = False
    else:
        task.status = "success"
        task.error_message = None
        task.message = "物理文件清理完成。"
        task.history_hidden = True
    db.session.commit()
    return {"task_id": task.id, "status": task.status, "removed_count": removed, "errors": errors}


def resume_cleanup_tasks() -> int:
    """Retry interrupted cleanup work during application startup."""
    rows = Task.query.filter(
        Task.type == "artifact_cleanup",
        Task.status.in_(["pending", "running"]),
    ).order_by(Task.created_at.asc()).all()
    for row in rows:
        process_cleanup_task(row)
    return len(rows)


def _finish_delete(cleanup_task: Task | None) -> dict:
    db.session.commit()
    if not cleanup_task:
        return {"cleanup_task_id": None, "cleanup_status": "not_required"}
    task_id = cleanup_task.id
    result = process_cleanup_task(cleanup_task)
    return {"cleanup_task_id": task_id, "cleanup_status": result["status"]}


def delete_dataset(dataset: Dataset, *, actor=None) -> dict:
    blockers = dataset_delete_blockers(dataset)
    if blockers:
        raise DeletionConflict("DATASET_DELETE_BLOCKED", "数据集仍被运行任务或联合索引使用。", blockers)

    dataset_id = dataset.id
    indexes = AnnIndex.query.filter_by(dataset_id=dataset_id).all()
    documents = KnowledgeDocument.query.filter_by(dataset_id=dataset_id).all()
    artifacts = []
    if dataset.file_path and Dataset.query.filter(
        Dataset.id != dataset_id, Dataset.file_path == dataset.file_path
    ).count() == 0:
        artifacts.append(_managed_artifact(dataset.file_path, "RAW_DIR"))
    artifacts.extend([
        _managed_artifact(dataset.vector_path, "CACHE_DIR"),
        _managed_artifact(dataset.scatter_cache_path, "CACHE_DIR"),
    ])
    for index in indexes:
        artifacts.extend([
            _managed_artifact(index.index_path, "INDEX_DIR"),
            _managed_artifact(index.preprocess_path, "INDEX_DIR"),
        ])
    for document in documents:
        if document.source_type != "builtin":
            artifacts.append(_managed_artifact(document.stored_path, "KNOWLEDGE_DIR"))
    artifacts = _dedupe_artifacts(artifacts)

    task_ids = [value for (value,) in db.session.query(Task.id).filter(Task.dataset_id == dataset_id).all()]
    reference_keys = (
        "dataset_id", "dataset_ids", "target_dataset_ids", "query_dataset_id", "source_dataset_id"
    )
    for task in Task.query.filter(
        or_(Task.dataset_id != dataset_id, Task.dataset_id.is_(None))
    ).all():
        request_data = _json_object(task.request_json)
        if task.status in TERMINAL_TASK_STATUSES and any(
            _request_references(request_data, key, dataset_id) for key in reference_keys
        ):
            task.history_hidden = True
    index_ids = [row.id for row in indexes]
    experiment_ids = [value for (value,) in db.session.query(IndexExperiment.id).filter_by(dataset_id=dataset_id).all()]
    document_ids = [row.id for row in documents]
    chunk_ids = [
        value for (value,) in db.session.query(KnowledgeChunk.id).filter(
            KnowledgeChunk.document_id.in_(document_ids) if document_ids else False
        ).all()
    ]

    if task_ids:
        AiRun.query.filter(AiRun.search_task_id.in_(task_ids)).update({AiRun.search_task_id: None}, synchronize_session=False)
        AiToolCall.query.filter(AiToolCall.task_id.in_(task_ids)).update({AiToolCall.task_id: None}, synchronize_session=False)
    if document_ids:
        AiProviderCall.query.filter(AiProviderCall.document_id.in_(document_ids)).update(
            {AiProviderCall.document_id: None}, synchronize_session=False
        )
    if chunk_ids:
        AiCitation.query.filter(AiCitation.chunk_id.in_(chunk_ids)).update(
            {AiCitation.chunk_id: None}, synchronize_session=False
        )

    QueryLog.query.filter(
        or_(QueryLog.dataset_id == dataset_id, QueryLog.index_id.in_(index_ids) if index_ids else False)
    ).delete(synchronize_session=False)
    JointQueryLog.query.filter_by(query_dataset_id=dataset_id).delete(synchronize_session=False)
    IndexEvaluation.query.filter_by(dataset_id=dataset_id).delete(synchronize_session=False)
    if index_ids:
        AnnIndex.query.filter(AnnIndex.id.in_(index_ids)).delete(synchronize_session=False)
    if experiment_ids:
        IndexExperimentRun.query.filter(IndexExperimentRun.experiment_id.in_(experiment_ids)).delete(synchronize_session=False)
        IndexExperiment.query.filter(IndexExperiment.id.in_(experiment_ids)).delete(synchronize_session=False)
    if chunk_ids:
        KnowledgeChunk.query.filter(KnowledgeChunk.id.in_(chunk_ids)).delete(synchronize_session=False)
    if document_ids:
        KnowledgeDocument.query.filter(KnowledgeDocument.id.in_(document_ids)).delete(synchronize_session=False)
    if task_ids:
        Task.query.filter(Task.id.in_(task_ids)).delete(synchronize_session=False)
    Cell.query.filter_by(dataset_id=dataset_id).delete(synchronize_session=False)
    DatasetPermission.query.filter_by(dataset_id=dataset_id).delete(synchronize_session=False)
    AuditLog.query.filter_by(dataset_id=dataset_id).update({AuditLog.dataset_id: None}, synchronize_session=False)

    name = dataset.name
    db.session.delete(dataset)
    record_audit(
        "dataset.deleted", actor=actor, resource_type="dataset", resource_id=dataset_id,
        details={"name": name},
    )
    cleanup = _queue_cleanup(artifacts, actor_id=getattr(actor, "id", None), label=f"数据集“{name}”")
    return _finish_delete(cleanup)


def delete_ann_index(index: AnnIndex, *, actor=None) -> dict:
    blockers = ann_index_delete_blockers(index)
    if blockers:
        raise DeletionConflict("ANN_INDEX_DELETE_BLOCKED", "索引仍在构建、评估或被任务使用。", blockers)
    artifacts = _dedupe_artifacts([
        _managed_artifact(index.index_path, "INDEX_DIR"),
        _managed_artifact(index.preprocess_path, "INDEX_DIR"),
    ])
    index_id = index.id
    dataset = db.session.get(Dataset, index.dataset_id)
    for task in Task.query.all():
        if (
            task.status in TERMINAL_TASK_STATUSES
            and _request_references(_json_object(task.request_json), "index_id", index_id)
        ):
            task.history_hidden = True
    QueryLog.query.filter_by(index_id=index_id).delete(synchronize_session=False)
    IndexEvaluation.query.filter_by(index_id=index_id).update(
        {IndexEvaluation.index_id: None}, synchronize_session=False
    )
    db.session.delete(index)
    db.session.flush()
    if dataset and dataset.status == "indexed":
        remaining = AnnIndex.query.filter(
            AnnIndex.dataset_id == dataset.id,
            AnnIndex.status == "ready",
            AnnIndex.lifecycle == "active",
        ).count()
        if remaining == 0:
            dataset.status = "processed"
    record_audit(
        "index.deleted", actor=actor, resource_type="ann_index", resource_id=index_id,
        dataset_id=dataset.id if dataset else None,
    )
    cleanup = _queue_cleanup(artifacts, actor_id=getattr(actor, "id", None), label="ANN 索引")
    return _finish_delete(cleanup)


def delete_joint_index(joint_index: JointIndex, *, actor=None) -> dict:
    blockers = joint_index_delete_blockers(joint_index)
    if blockers:
        raise DeletionConflict("JOINT_INDEX_DELETE_BLOCKED", "联合索引仍在构建或被任务使用。", blockers)
    artifacts = _dedupe_artifacts([
        _managed_artifact(joint_index.index_path, "INDEX_DIR"),
        _managed_artifact(joint_index.vector_path, "CACHE_DIR"),
        _managed_artifact(joint_index.umap_path, "CACHE_DIR"),
        _managed_artifact(joint_index.mapping_path, "CACHE_DIR"),
    ])
    joint_id = joint_index.id
    referenced_tasks = [
        row for row in Task.query.all()
        if _request_references(_json_object(row.request_json), "joint_index_id", joint_id)
    ]
    for task in referenced_tasks:
        if task.status in TERMINAL_TASK_STATUSES:
            task.history_hidden = True
    JointQueryLog.query.filter_by(joint_index_id=joint_id).delete(synchronize_session=False)
    JointIndexDataset.query.filter_by(joint_index_id=joint_id).delete(synchronize_session=False)
    db.session.delete(joint_index)
    record_audit(
        "joint_index.deleted", actor=actor, resource_type="joint_index", resource_id=joint_id,
        details={"name": joint_index.name},
    )
    cleanup = _queue_cleanup(artifacts, actor_id=getattr(actor, "id", None), label="联合索引")
    return _finish_delete(cleanup)


def remove_experiment(experiment: IndexExperiment, *, actor=None) -> None:
    if experiment.status in {"pending", "running"}:
        raise DeletionConflict(
            "INDEX_EXPERIMENT_RUNNING", "进行中的实验不能从历史移除。",
            [_blocker("index_experiment", experiment.id, "实验仍在运行", status=experiment.status)],
        )
    experiment.history_hidden = True
    record_audit(
        "index_experiment.history_hidden", actor=actor, resource_type="index_experiment",
        resource_id=experiment.id, dataset_id=experiment.dataset_id,
    )
    db.session.commit()


def remove_evaluation(evaluation: IndexEvaluation, *, actor=None) -> None:
    if evaluation.status in {"pending", "running"}:
        raise DeletionConflict(
            "INDEX_EVALUATION_RUNNING", "进行中的评估不能从历史移除。",
            [_blocker("index_evaluation", evaluation.id, "评估仍在运行", status=evaluation.status)],
        )
    evaluation.history_hidden = True
    record_audit(
        "index_evaluation.history_hidden", actor=actor, resource_type="index_evaluation",
        resource_id=evaluation.id, dataset_id=evaluation.dataset_id,
    )
    db.session.commit()


def remove_task(task: Task, *, actor=None) -> None:
    if task.status in ACTIVE_TASK_STATUSES:
        raise DeletionConflict(
            "TASK_RUNNING", "进行中的任务不能从历史移除。",
            [_blocker("task", task.id, task.message or "任务仍在运行", status=task.status)],
        )
    if task.type == "artifact_cleanup" and task.status == "error":
        raise DeletionConflict(
            "CLEANUP_RETRY_REQUIRED", "物理文件尚未清理完成，请先重试清理。",
            [_blocker("task", task.id, "清理任务仍需重试", status=task.status)],
        )
    task.history_hidden = True
    record_audit(
        "task.history_hidden", actor=actor, resource_type="task", resource_id=task.id,
        dataset_id=task.dataset_id, details={"type": task.type},
    )
    db.session.commit()


def remove_terminal_tasks_for_user(user_id: int, *, actor=None) -> int:
    rows = Task.query.filter(
        Task.created_by_id == user_id,
        Task.history_hidden.is_(False),
        Task.status.in_(TERMINAL_TASK_STATUSES),
        or_(Task.type != "artifact_cleanup", Task.status != "error"),
    ).all()
    for row in rows:
        row.history_hidden = True
    record_audit(
        "task.history_cleared", actor=actor, resource_type="task_history",
        details={"count": len(rows)},
    )
    db.session.commit()
    return len(rows)


def delete_knowledge_document(document: KnowledgeDocument, *, actor=None) -> dict:
    blockers = document_delete_blockers(document)
    if blockers:
        code = "BUILTIN_IMMUTABLE" if document.source_type == "builtin" else "AI_KNOWLEDGE_PROCESSING"
        message = "内置知识资料不可删除。" if document.source_type == "builtin" else "知识资料仍在处理中，暂不能删除。"
        raise DeletionConflict(code, message, blockers)
    artifacts = _dedupe_artifacts([_managed_artifact(document.stored_path, "KNOWLEDGE_DIR")])
    document_id = document.id
    chunk_ids = [value for (value,) in db.session.query(KnowledgeChunk.id).filter_by(document_id=document_id).all()]
    if chunk_ids:
        AiCitation.query.filter(AiCitation.chunk_id.in_(chunk_ids)).update(
            {AiCitation.chunk_id: None}, synchronize_session=False
        )
    AiProviderCall.query.filter_by(document_id=document_id).update(
        {AiProviderCall.document_id: None}, synchronize_session=False
    )
    if chunk_ids:
        KnowledgeChunk.query.filter(KnowledgeChunk.id.in_(chunk_ids)).delete(synchronize_session=False)
    dataset_id = document.dataset_id
    scope = document.scope
    db.session.delete(document)
    record_audit(
        "ai.knowledge_deleted", actor=actor, resource_type="knowledge_document",
        resource_id=document_id, dataset_id=dataset_id, details={"scope": scope},
    )
    cleanup = _queue_cleanup(artifacts, actor_id=getattr(actor, "id", None), label="知识资料")
    return _finish_delete(cleanup)


def delete_ai_conversation(conversation: AiConversation, *, actor=None) -> None:
    blockers = conversation_delete_blockers(conversation)
    if blockers:
        raise DeletionConflict("AI_CONVERSATION_RUNNING", "AI 会话仍有进行中的任务。", blockers)
    conversation_id = conversation.id
    run_ids = [run.id for run in conversation.runs]
    message_ids = [message.id for message in conversation.messages]
    task_ids = [run.search_task_id for run in conversation.runs if run.search_task_id]
    task_ids.extend(tool.task_id for run in conversation.runs for tool in run.tool_calls if tool.task_id)

    if run_ids:
        AiProviderCall.query.filter(AiProviderCall.run_id.in_(run_ids)).update(
            {AiProviderCall.run_id: None}, synchronize_session=False
        )
        AiRun.query.filter(AiRun.context_run_id.in_(run_ids)).update(
            {AiRun.context_run_id: None}, synchronize_session=False
        )
        AiStreamEvent.query.filter(AiStreamEvent.run_id.in_(run_ids)).delete(synchronize_session=False)
        AiToolCall.query.filter(AiToolCall.run_id.in_(run_ids)).delete(synchronize_session=False)
    if message_ids:
        AiCitation.query.filter(AiCitation.message_id.in_(message_ids)).delete(synchronize_session=False)
    if run_ids:
        AiRun.query.filter(AiRun.id.in_(run_ids)).delete(synchronize_session=False)
    if message_ids:
        AiMessage.query.filter(AiMessage.id.in_(message_ids)).delete(synchronize_session=False)
    for task in Task.query.filter(Task.id.in_(set(task_ids)) if task_ids else False).all():
        if task.source == "ai":
            task.history_hidden = True
    AiConversation.query.filter_by(id=conversation_id).delete(synchronize_session=False)
    record_audit(
        "ai.conversation_deleted", actor=actor, resource_type="ai_conversation",
        resource_id=conversation_id,
    )
    db.session.commit()
