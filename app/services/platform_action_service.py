"""Shared, permission-checked platform actions used by HTTP routes and AI approvals."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json

from app.extensions import db
from app.models import AnnIndex, Dataset, KnowledgeDocument, Task
from app.services.access_service import can_edit_dataset, can_view_task
from app.services.audit_service import record_audit


class ActionValidationError(ValueError):
    pass


class ActionPermissionError(PermissionError):
    pass


def _int(value, default: int, low: int, high: int) -> int:
    try:
        parsed = int(default if value is None else value)
    except (TypeError, ValueError) as exc:
        raise ActionValidationError("操作参数必须是整数。") from exc
    if parsed < low or parsed > high:
        raise ActionValidationError(f"操作参数必须位于 {low}–{high}。")
    return parsed


def _dataset_for_edit(reference, user) -> Dataset:
    dataset = None
    try:
        dataset = db.session.get(Dataset, int(reference))
    except (TypeError, ValueError):
        name = str(reference or "").strip()
        if name:
            dataset = Dataset.query.filter(Dataset.name == name).first()
    if not dataset:
        raise ActionValidationError("未找到目标数据集。")
    if not can_edit_dataset(dataset, user):
        raise ActionPermissionError("需要数据集 Editor 权限才能执行该操作。")
    return dataset


def normalize_action(action: str, args: dict, user) -> tuple[dict, dict, str]:
    """Return canonical args, a state snapshot, and a human impact description."""
    args = args if isinstance(args, dict) else {}
    if action == "submit_dataset_processing":
        dataset = _dataset_for_edit(args.get("dataset_id") or args.get("dataset_reference"), user)
        if dataset.status not in {"uploaded", "error"}:
            raise ActionValidationError("只有已上传或处理失败的数据集可以重新处理。")
        canonical = {"dataset_id": dataset.id}
        return canonical, {"dataset_status": dataset.status}, f"处理数据集「{dataset.name}」并生成向量缓存。"

    if action in {"submit_index_build", "submit_index_experiment", "submit_index_evaluation"}:
        dataset = _dataset_for_edit(args.get("dataset_id") or args.get("dataset_reference"), user)
        if dataset.status not in {"processed", "indexed"}:
            raise ActionValidationError("数据集需要先完成处理。")
        state = {"dataset_status": dataset.status}
        if action == "submit_index_build":
            algorithm = str(args.get("algorithm") or "hnswlib_hnsw")
            metric = str(args.get("metric") or "l2")
            if metric not in {"l2", "cosine"}:
                raise ActionValidationError("距离度量只支持 l2 或 cosine。")
            from app.services.ann_backend_service import algorithm_catalog
            catalog = {row["key"]: row for row in algorithm_catalog(n_cells=dataset.n_cells, dim=dataset.vector_dim)}
            if algorithm not in catalog or not catalog[algorithm].get("available"):
                raise ActionValidationError("所选 ANN 算法当前不可用。")
            params = dict(args.get("params") or {})
            params.setdefault("M", _int(args.get("M"), 16, 2, 128))
            params.setdefault("ef_construction", _int(args.get("ef_construction"), 200, 2, 1000))
            params.setdefault("ef_search", _int(args.get("ef_search"), 100, 1, 1000))
            if int(params["ef_construction"]) < int(params["M"]):
                raise ActionValidationError("ef_construction 必须大于等于 M。")
            canonical = {"dataset_id": dataset.id, "algorithm": algorithm, "metric": metric, "params": params}
            return canonical, state, f"为「{dataset.name}」构建一个 {algorithm} 索引。"
        if action == "submit_index_experiment":
            metric = str(args.get("metric") or "l2")
            if metric not in {"l2", "cosine"}:
                raise ActionValidationError("距离度量只支持 l2 或 cosine。")
            canonical = {
                "dataset_id": dataset.id, "metric": metric,
                "sample_size": _int(args.get("sample_size"), 100, 1, 200),
                "top_k": _int(args.get("top_k"), 10, 1, 100),
                "seed": _int(args.get("seed"), 42, 0, 2_147_483_647),
                "repetitions": _int(args.get("repetitions"), 3, 1, 10),
                "warmup_count": _int(args.get("warmup_count"), 10, 0, 200),
                "candidate_keys": list(args.get("candidate_keys") or []),
            }
            return canonical, state, f"为「{dataset.name}」提交候选索引实验。"
        index_id = _int(args.get("index_id"), 0, 1, 2_147_483_647)
        index = db.session.get(AnnIndex, index_id)
        if not index or index.dataset_id != dataset.id or index.status != "ready":
            raise ActionValidationError("请选择该数据集的 ready 索引。")
        canonical = {
            "dataset_id": dataset.id, "index_id": index.id,
            "sample_size": _int(args.get("sample_size"), 100, 1, 200),
            "top_k": _int(args.get("top_k"), 10, 1, 100),
            "seed": _int(args.get("seed"), 42, 0, 2_147_483_647),
        }
        state["index_status"] = index.status
        return canonical, state, f"评估「{dataset.name}」的索引 #{index.id}。"

    if action == "submit_joint_index_build":
        raw_ids = args.get("dataset_ids") or args.get("target_dataset_ids") or []
        dataset_ids = list(dict.fromkeys(int(value) for value in raw_ids))
        if len(dataset_ids) < 2:
            raise ActionValidationError("联合索引至少需要两个数据集。")
        datasets = [_dataset_for_edit(value, user) for value in dataset_ids]
        if any(row.status not in {"processed", "indexed"} for row in datasets):
            raise ActionValidationError("所有数据集都必须先完成处理。")
        metric = str(args.get("metric") or "l2")
        if metric not in {"l2", "cosine"}:
            raise ActionValidationError("距离度量只支持 l2 或 cosine。")
        canonical = {
            "name": str(args.get("name") or "AI 联合索引")[:200],
            "dataset_ids": dataset_ids, "metric": metric,
            "M": _int(args.get("M"), 16, 2, 128),
            "ef_construction": _int(args.get("ef_construction"), 200, 2, 1000),
            "ef_search": _int(args.get("ef_search"), 100, 1, 1000),
            "n_pcs": _int(args.get("n_pcs"), 50, 2, 200),
            "n_top_genes": _int(args.get("n_top_genes"), 2000, 50, 10000),
            "min_common_genes": _int(args.get("min_common_genes"), 500, 1, 50000),
            "owner_id": user.id,
        }
        if canonical["ef_construction"] < canonical["M"]:
            raise ActionValidationError("ef_construction 必须大于等于 M。")
        state = {"dataset_statuses": {str(row.id): row.status for row in datasets}}
        return canonical, state, f"使用 {len(datasets)} 个数据集构建联合索引。"

    if action == "reindex_knowledge_document":
        document_id = _int(args.get("document_id"), 0, 1, 2_147_483_647)
        document = db.session.get(KnowledgeDocument, document_id)
        from app.ai.knowledge import can_manage_document
        if not document or not can_manage_document(document, user):
            raise ActionPermissionError("知识文档不存在或无权维护。")
        canonical = {"document_id": document.id}
        return canonical, {"document_updated_at": document.updated_at.isoformat()}, f"重建知识文档「{document.title}」的索引。"

    if action == "create_personal_knowledge_note":
        title = str(args.get("title") or "个人知识笔记").strip()[:300]
        content = str(args.get("content") or "").strip()
        if not content or len(content) > 20_000:
            raise ActionValidationError("个人笔记内容必须为 1–20,000 个字符。")
        canonical = {"title": title, "content": content}
        return canonical, {"owner_id": user.id}, f"创建私人知识笔记「{title}」。"

    raise ActionValidationError("该操作不在 AI 安全写工具白名单中。")


def idempotency_key(run_id: int, user_id: int, action: str, args: dict) -> str:
    raw = json.dumps([run_id, user_id, action, args], ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def execute_action(action: str, args: dict, user, app) -> dict:
    """Revalidate and submit one approved action. Caller owns transaction state."""
    canonical, _, _ = normalize_action(action, args, user)
    from app.tasks import (
        executor, run_build_index_task, run_build_joint_index_task,
        run_index_evaluation_task, run_index_experiment_task, run_process_task,
    )
    now = datetime.utcnow()

    if action == "submit_dataset_processing":
        task = Task(type="process", status="pending", progress=0, message="任务已提交，等待执行...",
                    dataset_id=canonical["dataset_id"], created_by_id=user.id, updated_at=now)
        db.session.add(task)
        record_audit("dataset.process_submitted", actor=user, resource_type="dataset",
                     resource_id=canonical["dataset_id"], dataset_id=canonical["dataset_id"], details={"source": "ai_assistant"})
        db.session.commit()
        executor.submit(run_process_task, task.id, canonical["dataset_id"], app)
        return {"task_id": task.id, "task_type": task.type}

    if action == "submit_index_build":
        task = Task(type="build_index", status="pending", progress=0, message="任务已提交，等待执行...",
                    dataset_id=canonical["dataset_id"], created_by_id=user.id, updated_at=now)
        db.session.add(task)
        record_audit("index.build_submitted", actor=user, resource_type="dataset",
                     resource_id=canonical["dataset_id"], dataset_id=canonical["dataset_id"],
                     details={"source": "ai_assistant", "algorithm": canonical["algorithm"], "metric": canonical["metric"]})
        db.session.commit()
        executor.submit(run_build_index_task, task.id, canonical["dataset_id"], canonical, app)
        return {"task_id": task.id, "task_type": task.type}

    if action == "submit_index_experiment":
        from app.services.index_experiment_service import create_index_experiment
        experiment = create_index_experiment(**canonical)
        experiment.created_by_id = user.id
        task = Task(type="index_experiment", status="pending", progress=0,
                    message="候选索引实验已提交，等待执行...", dataset_id=canonical["dataset_id"],
                    created_by_id=user.id, updated_at=now)
        db.session.add(task)
        record_audit("index_experiment.created", actor=user, resource_type="index_experiment",
                     resource_id=experiment.id, dataset_id=canonical["dataset_id"], details={"source": "ai_assistant"})
        db.session.commit()
        executor.submit(run_index_experiment_task, task.id,
                        {"dataset_id": canonical["dataset_id"], "experiment_id": experiment.id}, app)
        return {"task_id": task.id, "task_type": task.type, "experiment_id": experiment.id}

    if action == "submit_index_evaluation":
        task = Task(type="index_evaluation", status="pending", progress=0,
                    message="索引评估任务已提交。", dataset_id=canonical["dataset_id"],
                    created_by_id=user.id, updated_at=now)
        db.session.add(task)
        record_audit("index.evaluation_submitted", actor=user, resource_type="ann_index",
                     resource_id=canonical["index_id"], dataset_id=canonical["dataset_id"], details={"source": "ai_assistant"})
        db.session.commit()
        executor.submit(run_index_evaluation_task, task.id, canonical, app)
        return {"task_id": task.id, "task_type": task.type}

    if action == "submit_joint_index_build":
        task = Task(type="build_joint_index", status="pending", progress=0,
                    message="联合索引构建任务已提交。", created_by_id=user.id, updated_at=now)
        db.session.add(task)
        record_audit("joint_index.build_submitted", actor=user, resource_type="joint_index",
                     details={"source": "ai_assistant", "dataset_ids": canonical["dataset_ids"]})
        db.session.commit()
        executor.submit(run_build_joint_index_task, task.id, canonical, app)
        return {"task_id": task.id, "task_type": task.type}

    if action == "reindex_knowledge_document":
        document = db.session.get(KnowledgeDocument, canonical["document_id"])
        document.status = "pending"
        document.error_message = None
        record_audit("ai.knowledge_reindexed", actor=user, resource_type="knowledge_document", resource_id=document.id)
        db.session.commit()
        from app.ai.knowledge import submit_document_processing
        submit_document_processing(app, document.id)
        return {"document_id": document.id, "status": "pending"}

    if action == "create_personal_knowledge_note":
        from app.ai.knowledge import create_personal_note, submit_document_processing
        document = create_personal_note(title=canonical["title"], content=canonical["content"], user=user)
        record_audit("ai.knowledge_created", actor=user, resource_type="knowledge_document",
                     resource_id=document.id, details={"scope": "personal", "source": "ai_assistant"})
        db.session.commit()
        submit_document_processing(app, document.id)
        return {"document_id": document.id, "status": "pending"}

    raise ActionValidationError("未知操作。")

