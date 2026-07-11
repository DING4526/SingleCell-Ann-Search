"""Global assistant orchestration with sanitized page context and approved actions."""
from __future__ import annotations

from datetime import datetime, timedelta
import json
import re
from urllib.parse import urlencode

from app.ai.prompts import (
    ASSISTANT_ANSWER_SYSTEM, ASSISTANT_EXAMPLES, GLOBAL_ASSISTANT_SYSTEM,
    PLATFORM_INVARIANTS, PROMPT_REVISION, QUALITY_REPAIR_SYSTEM,
)
from app.ai.schemas import AssistantTurnDecision
from app.extensions import db
from app.models import (
    AiCitation, AiConversation, AiMessage, AiModelConfig, AiRun, AiToolCall,
    AnnIndex, Cell, Dataset, JointIndex, Task, User,
)
from app.services.access_service import (
    accessible_datasets_query, accessible_tasks_query, can_view_dataset,
    can_view_task, effective_dataset_role,
)
from app.services.audit_service import record_audit
from app.services.platform_action_service import idempotency_key, normalize_action
from app.ai.tools import write_tool_contracts


ROUTE_REGISTRY = {
    "overview": {"path": "/overview", "params": set()},
    "datasets": {"path": "/datasets", "params": set()},
    "dataset_detail": {"path": "/datasets/{dataset_id}", "params": {"dataset_id", "access"}},
    "index_lab": {"path": "/index-lab", "params": {"dataset", "experiment"}},
    "joint_indexes": {"path": "/joint-indexes", "params": set()},
    "query_lab": {"path": "/query-lab", "params": {"dataset", "history_id", "index", "cell", "top_k", "filter_cell_type"}},
    "access": {"path": "/access", "params": set()},
    "ai_analysis": {"path": "/ai-analysis", "params": {"conversation_id", "prompt", "dataset"}},
    "ai_knowledge": {"path": "/ai-knowledge", "params": {"dataset"}},
    "ai_assistant": {"path": "/ai-assistant", "params": {"conversation_id"}},
}

_ALLOWED_PAGE_KEYS = {"route", "path", "name", "params", "query", "resources", "filters", "label"}
_ALLOWED_RESOURCE_KEYS = {"dataset_id", "index_id", "joint_index_id", "task_id", "history_id", "document_id"}
_ALLOWED_FILTER_KEYS = {"status", "mode", "source", "top_k", "cell_type", "keyword"}


def _short_scalar(value, max_chars: int = 160):
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:max_chars]
    return None


def sanitize_page_context(raw, user: User) -> dict:
    """Accept only route/resource/filter metadata and revalidate referenced resources."""
    if not isinstance(raw, dict):
        return {}
    cleaned: dict = {}
    for key in _ALLOWED_PAGE_KEYS:
        value = raw.get(key)
        if key in {"route", "path", "name", "label"}:
            scalar = _short_scalar(value)
            if scalar is not None:
                cleaned[key] = scalar
    path = str(cleaned.get("path") or cleaned.get("route") or "")
    if path and not any(
        path == row["path"] or ("{" in row["path"] and path.startswith(row["path"].split("{")[0]))
        for row in ROUTE_REGISTRY.values()
    ):
        cleaned.pop("path", None)
        cleaned.pop("route", None)

    resources: dict[str, int] = {}
    raw_resources = raw.get("resources") if isinstance(raw.get("resources"), dict) else {}
    for key in _ALLOWED_RESOURCE_KEYS:
        value = raw_resources.get(key)
        if value is None:
            value = (raw.get("params") or {}).get(key) if isinstance(raw.get("params"), dict) else None
        if value is None:
            value = (raw.get("query") or {}).get(key) if isinstance(raw.get("query"), dict) else None
        try:
            resources[key] = int(value)
        except (TypeError, ValueError):
            continue
    if resources.get("dataset_id"):
        dataset = db.session.get(Dataset, resources["dataset_id"])
        if not dataset or not can_view_dataset(dataset, user):
            resources.pop("dataset_id", None)
    if resources.get("index_id"):
        index = db.session.get(AnnIndex, resources["index_id"])
        if not index or not index.dataset or not can_view_dataset(index.dataset, user):
            resources.pop("index_id", None)
    if resources.get("task_id"):
        task = db.session.get(Task, resources["task_id"])
        if not task or not can_view_task(task, user):
            resources.pop("task_id", None)
    if resources:
        cleaned["resources"] = resources

    filters = raw.get("filters") if isinstance(raw.get("filters"), dict) else {}
    safe_filters = {key: _short_scalar(filters[key]) for key in _ALLOWED_FILTER_KEYS if key in filters}
    safe_filters = {key: value for key, value in safe_filters.items() if value is not None}
    if safe_filters:
        cleaned["filters"] = safe_filters
    encoded = json.dumps(cleaned, ensure_ascii=False)
    return cleaned if len(encoded) <= 2000 else {"path": cleaned.get("path"), "resources": resources}


def _resource_context(user: User, page_context: dict) -> dict:
    datasets = accessible_datasets_query(user=user).order_by(Dataset.created_at.desc()).limit(60).all()
    page_dataset_id = ((page_context.get("resources") or {}).get("dataset_id"))
    dataset_rows = []
    ready_index_count = 0
    for dataset in datasets:
        indexes = [row for row in dataset.indexes if row.status == "ready" and (row.lifecycle or "active") == "active"]
        ready_index_count += len(indexes)
        row_data = {
            "id": dataset.id, "name": dataset.name, "status": dataset.status,
            "role": effective_dataset_role(dataset, user), "n_cells": dataset.n_cells,
            "ready_indexes": [{"id": row.id, "algorithm": row.algorithm, "metric": row.metric} for row in indexes[:6]],
        }
        if dataset.id == page_dataset_id:
            distributions = {}
            for field in ("cell_type", "disease", "age_group"):
                column = getattr(Cell, field)
                rows = (
                    db.session.query(column, db.func.count(Cell.id))
                    .filter(Cell.dataset_id == dataset.id)
                    .group_by(column)
                    .order_by(db.func.count(Cell.id).desc())
                    .limit(8).all()
                )
                distributions[field] = {str(value or "N/A"): int(count) for value, count in rows}
            row_data["distributions"] = distributions
        dataset_rows.append(row_data)
    tasks = (
        accessible_tasks_query(user=user)
        .filter(Task.history_hidden.is_(False))
        .order_by(Task.updated_at.desc())
        .limit(20)
        .all()
    )
    task_rows = [{
        "id": row.id, "type": row.type, "status": row.status, "progress": row.progress,
        "dataset_id": row.dataset_id, "message": (row.message or "")[:160],
    } for row in tasks]
    visible_dataset_ids = {row.id for row in datasets}
    joint_rows = []
    for joint in JointIndex.query.order_by(JointIndex.created_at.desc()).limit(30).all():
        source_ids = [item.dataset_id for item in joint.datasets if item.status == "included"]
        if source_ids and all(value in visible_dataset_ids for value in source_ids):
            joint_rows.append({"id": joint.id, "name": joint.name, "status": joint.status, "dataset_ids": source_ids})
    return {
        "page": page_context,
        "datasets": dataset_rows,
        "joint_indexes": joint_rows,
        "recent_tasks": task_rows,
        "evidence": {
            "dataset_count": len(dataset_rows),
            "ready_index_count": ready_index_count,
            "active_task_count": sum(row["status"] in {"pending", "running"} for row in task_rows),
        },
        "user": {"id": user.id, "username": user.username, "system_role": user.role},
    }


def _recent_dialogue(conversation_id: int, input_message_id: int | None) -> list[dict]:
    rows = (
        AiMessage.query.filter(AiMessage.conversation_id == conversation_id, AiMessage.id != input_message_id)
        .order_by(AiMessage.id.desc()).limit(8).all()
    )
    remaining = 5000
    result = []
    for row in reversed(rows):
        if remaining <= 0:
            break
        content = (row.content or "")[:min(1000, remaining)]
        remaining -= len(content)
        result.append({"role": row.role, "content": content})
    return result


def _explicit_navigation(prompt: str) -> bool:
    return bool(re.search(r"(?:打开|进入|跳转|带我去|前往|导航到)", prompt or ""))


def _should_use_analysis_executor(prompt: str, conversation_id: int) -> bool:
    """Route real scientific retrieval and evidence follow-ups to the analysis engine."""
    text = (prompt or "").strip()
    scientific = bool(
        re.search(r"(?:找|查找|检索|查询|搜索).{0,20}(?:相似|近邻|细胞)", text, re.I)
        or re.search(r"(?:相似|近邻|细胞).{0,20}(?:找|查找|检索|查询|搜索)", text, re.I)
        or re.search(r"(?:Fan-?out|联合索引|跨数据集).{0,20}(?:检索|查询|比较|对比)", text, re.I)
        or re.search(r"(?:比较|对比).{0,30}(?:数据集|检索结果|细胞分布)", text, re.I)
    )
    if scientific:
        return True
    follow_up = bool(re.search(
        r"(?:这些|上述|上一轮|刚才|检索结果|结果).{0,24}(?:分布|疾病|年龄|类型|距离|解释|比较|差异|说明|意味)",
        text, re.I,
    ))
    if not follow_up:
        return False
    return AiRun.query.filter(
        AiRun.conversation_id == conversation_id,
        AiRun.surface == "analysis",
        AiRun.status.in_(["success", "cancelled"]),
    ).first() is not None


def _queue_analysis_executor(app, run: AiRun) -> None:
    """Reuse the same run and conversation while switching to scientific planning."""
    from app.ai.service import set_run_phase, submit_planning

    run.surface = "analysis"
    run.intent = "analysis_request"
    run.status = "queued"
    run.progress = 5
    run.prompt_revision = PROMPT_REVISION
    set_run_phase(run, "planning", "正在生成可确认的科学分析计划。")
    db.session.commit()
    submit_planning(app, run.id)


def _deterministic_decision(prompt: str, resource_context: dict) -> AssistantTurnDecision | None:
    """Resolve unambiguous, safety-critical turns without paying model latency."""
    text = (prompt or "").strip()
    if re.search(r"(?:删除|转移所有权|公开.*私有|分享给所有人|API\s*Key|密钥)", text, re.I):
        return AssistantTurnDecision(
            intent="answer_only",
            direct_answer="这个请求涉及删除、权限、所有权或敏感凭据，AI 助手不会执行。请使用对应管理页面的人工入口，并在操作前核对影响。",
        )
    if re.search(r"(?:最相似|相似细胞|近邻细胞|跨数据集.*比较)", text):
        return AssistantTurnDecision(
            intent="analysis_handoff",
            direct_answer="这个请求需要真实单细胞检索，我会在当前会话生成科学分析计划，并在执行 ANN 前让你确认。",
            handoff_prompt=text,
        )
    if re.search(r"(?:主要|常见|最多|分布).{0,8}(?:细胞类型|疾病|年龄)|(?:细胞类型|疾病|年龄).{0,8}(?:主要|常见|最多|分布)", text):
        datasets = resource_context.get("datasets") or []
        page_dataset_id = ((resource_context.get("page") or {}).get("resources") or {}).get("dataset_id")
        selected = next((row for row in datasets if row.get("id") == page_dataset_id), None)
        if selected and selected.get("distributions"):
            field, label = (
                ("cell_type", "细胞类型") if "细胞类型" in text
                else ("disease", "疾病") if "疾病" in text else ("age_group", "年龄组")
            )
            values = (selected["distributions"].get(field) or {})
            rows = list(values.items())[:5]
            description = "、".join(f"{name}（{count} 个）" for name, count in rows) or "暂无可用标注"
            return AssistantTurnDecision(
                intent="answer_only",
                direct_answer=f"{selected.get('name')} 的主要{label}为：{description}。",
                supporting_points=["以上来自当前数据集的实时元数据统计，不是模型推测。"],
            )
    if "数据集" in text and re.search(r"(?:介绍|概况|信息|详情|是什么|怎么样|状态)", text):
        datasets = resource_context.get("datasets") or []
        page_dataset_id = ((resource_context.get("page") or {}).get("resources") or {}).get("dataset_id")
        named = [row for row in datasets if str(row.get("name") or "").lower() in text.lower()]
        selected = named[0] if len(named) == 1 else next(
            (row for row in datasets if row.get("id") == page_dataset_id), None
        )
        if selected:
            status_text = {
                "uploaded": "已上传，尚未完成向量处理",
                "processing": "正在处理",
                "processed": "已完成向量处理，可以构建索引",
                "indexed": "已完成向量处理并且已有索引",
                "error": "处理失败，需要先查看任务错误",
            }.get(str(selected.get("status") or ""), str(selected.get("status") or "未知"))
            role_text = {
                "admin": "管理员",
                "owner": "所有者",
                "editor": "编辑者",
                "viewer": "只读查看者",
            }.get(str(selected.get("role") or ""), str(selected.get("role") or "未知权限"))
            indexes = selected.get("ready_indexes") or []
            cell_text = (
                f"包含 {selected['n_cells']} 个细胞"
                if selected.get("n_cells") is not None else "细胞数量尚未记录"
            )
            index_text = "、".join(
                f"{row.get('algorithm')}（{row.get('metric')}）" for row in indexes
            ) or "暂无 ready/active 索引"
            return AssistantTurnDecision(
                intent="answer_only",
                direct_answer=(
                    f"{selected.get('name')} 是当前可访问的单细胞数据集，{cell_text}。"
                    f"当前状态为 {selected.get('status')}：{status_text}。"
                ),
                supporting_points=[
                    f"你的有效权限是{role_text}。",
                    f"当前可用索引：{index_text}。",
                    "可以继续查看统计分布，或前往 Query Lab 进行相似细胞检索。",
                ],
            )
    if not _explicit_navigation(text):
        return None
    route_terms = [
        ("数据资源", "datasets"), ("数据集列表", "datasets"),
        ("联合索引", "joint_indexes"), ("检索实验室", "query_lab"),
        ("索引实验室", "index_lab"), ("权限管理", "access"),
        ("AI Analysis", "ai_analysis"), ("AI 分析", "ai_analysis"),
        ("知识库", "ai_knowledge"), ("全局 AI 助手", "ai_assistant"), ("概览", "overview"),
    ]
    matches = [(term, target) for term, target in route_terms if term.lower() in text.lower()]
    params: dict = {}
    if len(matches) == 1:
        target = matches[0][1]
        page_dataset_id = ((resource_context.get("page") or {}).get("resources") or {}).get("dataset_id")
        if target in {"query_lab", "index_lab", "ai_analysis", "ai_knowledge"} and page_dataset_id:
            params["dataset_id"] = page_dataset_id
        return AssistantTurnDecision(
            intent="navigate", direct_answer=f"正在打开{matches[0][0]}。",
            navigation_target=target, navigation_params=params,
        )
    if "数据集" in text:
        named = [row for row in resource_context.get("datasets") or [] if str(row.get("name") or "").lower() in text.lower()]
        if len(named) == 1:
            return AssistantTurnDecision(
                intent="navigate", direct_answer=f"正在打开数据集「{named[0]['name']}」。",
                navigation_target="dataset_detail", navigation_params={"dataset_id": named[0]["id"]},
            )
    return None


def _chinese_dominant(text: str) -> bool:
    sentences = [part.strip() for part in re.split(r"[。！？.!?]+", text or "") if part.strip()]
    if not sentences:
        return False
    return sum(bool(re.search(r"[\u4e00-\u9fff]", part)) for part in sentences) / len(sentences) >= 0.6


def _render_evidence(text: str, evidence: dict) -> str | None:
    unknown = False
    def replace(match):
        nonlocal unknown
        key = match.group(1)
        if key not in evidence:
            unknown = True
            return match.group(0)
        return str(evidence[key])
    rendered = re.sub(r"\{\{E:([a-zA-Z0-9_.-]+)\}\}", replace, text or "")
    return None if unknown else rendered


def _numbers_grounded(text: str, resource_context: dict) -> bool:
    """Resource numbers may be repeated, but every one must exist in trusted context."""
    observed = re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?", text or "")
    trusted = set(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?", json.dumps(resource_context, ensure_ascii=False)))
    return all(value in trusted for value in observed)


def _validated_answer(text: str, resource_context: dict, allowed_knowledge: set[str]) -> tuple[str | None, set[str]]:
    rendered = _render_evidence(text, resource_context["evidence"])
    cited = set(re.findall(r"\[(K:[^\]]+)\]", text or ""))
    valid = (
        rendered is not None
        and cited.issubset(allowed_knowledge)
        and _chinese_dominant(rendered)
        and _numbers_grounded(rendered, resource_context)
    )
    return (rendered if valid else None), cited


def _text_chunks(text: str, size: int = 48) -> list[str]:
    return [text[index:index + size] for index in range(0, len(text), size)]


def resolve_navigation(target: str | None, params: dict, user: User) -> dict | None:
    definition = ROUTE_REGISTRY.get(str(target or ""))
    if not definition:
        return None
    params = params if isinstance(params, dict) else {}
    params = dict(params)
    if target in {"query_lab", "index_lab", "ai_knowledge", "ai_analysis"} and params.get("dataset") is None:
        params["dataset"] = params.get("dataset_id")
    allowed = definition["params"]
    clean: dict[str, str | int] = {}
    for key in allowed:
        value = params.get(key)
        if value is None:
            continue
        clean[key] = int(value) if key in {"dataset_id", "dataset", "experiment", "history_id", "index", "cell", "top_k", "conversation_id"} else str(value)[:200]
    dataset_id = clean.get("dataset_id") or clean.get("dataset")
    if dataset_id:
        dataset = db.session.get(Dataset, int(dataset_id))
        if not dataset or not can_view_dataset(dataset, user):
            return None
    path = definition["path"]
    if "{dataset_id}" in path:
        if not clean.get("dataset_id"):
            return None
        path = path.format(dataset_id=clean.pop("dataset_id"))
    url = path + ("?" + urlencode(clean) if clean else "")
    return {"target": target, "path": url, "params": clean}


def _assistant_text(decision: AssistantTurnDecision, fallback: str) -> str:
    base = (decision.direct_answer or decision.clarification_question or fallback).strip()
    points = [str(item).strip() for item in decision.supporting_points if str(item).strip()]
    return "\n".join([base, *[f"- {item}" for item in points]])


def _merge_page_action_args(args: dict, page_context: dict) -> dict:
    merged = dict(args or {})
    resources = page_context.get("resources") if isinstance(page_context.get("resources"), dict) else {}
    for key in ("dataset_id", "index_id", "task_id", "document_id"):
        if merged.get(key) is None and resources.get(key) is not None:
            merged[key] = resources[key]
    return merged


def submit_assistant(app, run_id: int) -> None:
    from app.ai.service import ai_executor
    ai_executor.submit(run_assistant, app, run_id)


def run_assistant(app, run_id: int) -> None:
    with app.app_context():
        from app.ai.knowledge import retrieve_knowledge
        from app.ai.service import (
            _fail_run, _persist_citations, _record_run_provider_call, _update_usage,
            configured_provider, get_ai_settings, json_dumps, json_loads, set_run_phase,
        )
        from app.ai.streaming import emit_stream_event

        run = db.session.get(AiRun, run_id)
        if not run or run.status not in {"queued", "planning"}:
            return
        run.status = "planning"
        run.started_at = run.started_at or datetime.utcnow()
        set_run_phase(run, "planning", "正在理解当前页面和你的需求。")
        db.session.commit()
        try:
            user = db.session.get(User, run.user_id)
            model = db.session.get(AiModelConfig, run.model_config_id)
            if not user or not model:
                raise ValueError("助手用户或模型配置不存在。")
            prompt = run.input_message.content if run.input_message else ""
            page_context = sanitize_page_context(json_loads(run.page_context_json, {}), user)
            run.page_context_json = json_dumps(page_context)
            if _should_use_analysis_executor(prompt, run.conversation_id):
                _queue_analysis_executor(app, run)
                return
            resource_context = _resource_context(user, page_context)
            dataset_ids = []
            if (page_context.get("resources") or {}).get("dataset_id"):
                dataset_ids.append(page_context["resources"]["dataset_id"])
            hits = retrieve_knowledge(
                prompt, user=user, scopes=["platform", "dataset", "personal"],
                dataset_ids=dataset_ids, run_id=run.id, limit=get_ai_settings().default_knowledge_top_k,
            ) if get_ai_settings().rag_enabled else []
            knowledge_context = [{
                "key": row["key"], "title": row.get("title"), "heading": row.get("heading"),
                "content": row.get("content", "")[:1600],
            } for row in hits]
            messages = [
                {"role": "system", "content": GLOBAL_ASSISTANT_SYSTEM},
                {"role": "system", "content": ASSISTANT_EXAMPLES},
                {"role": "system", "content": PLATFORM_INVARIANTS},
                {"role": "system", "content": "实时平台上下文：" + json_dumps(resource_context)},
                {"role": "system", "content": "最近对话：" + json_dumps(_recent_dialogue(run.conversation_id, run.input_message_id))},
                {"role": "system", "content": "可引用知识：" + json_dumps(knowledge_context)},
                {"role": "system", "content": "安全写操作参数契约：" + json_dumps(write_tool_contracts())},
                {"role": "user", "content": prompt},
            ]
            decision = _deterministic_decision(prompt, resource_context)
            completion = None
            provider = None
            if decision is None:
                provider = configured_provider(model)
                completion = provider.complete_structured(
                    model=model.model_id, messages=messages, schema_model=AssistantTurnDecision, max_tokens=1400,
                )
                _update_usage(run, completion.usage)
                _record_run_provider_call(run, model, "assistant_decision", completion.usage, "success")
                decision = completion.value
            if decision.intent == "analysis_handoff":
                _queue_analysis_executor(app, run)
                return
            answer = _assistant_text(decision, "我已读取当前页面，但还需要更具体的问题。")
            allowed_knowledge = {row["key"] for row in hits}
            rendered, text_cited = _validated_answer(answer, resource_context, allowed_knowledge)
            cited = text_cited | set(decision.knowledge_keys)
            valid = rendered is not None and cited.issubset(allowed_knowledge)
            if not valid and completion is not None and provider is not None:
                repair = provider.complete_structured(
                    model=model.model_id,
                    messages=[*messages, {"role": "assistant", "content": completion.raw_text},
                              {"role": "system", "content": QUALITY_REPAIR_SYSTEM}],
                    schema_model=AssistantTurnDecision, max_tokens=1400,
                )
                _update_usage(run, repair.usage)
                _record_run_provider_call(run, model, "assistant_repair", repair.usage, "success")
                decision = repair.value
                completion = repair
                answer = _assistant_text(decision, "请补充你希望完成的具体平台操作。")
                rendered, text_cited = _validated_answer(answer, resource_context, allowed_knowledge)
                cited = text_cited | set(decision.knowledge_keys)
                valid = rendered is not None and cited.issubset(allowed_knowledge)
            answer = rendered if valid and rendered else "我暂时无法可靠完成这次理解。请明确说明目标页面、数据集或希望执行的操作。"

            stream_started = False
            stream_emitted = False
            if completion is not None and provider is not None and decision.intent in {"answer_only", "need_clarification"}:
                set_run_phase(run, "answer", "正在流式生成中文回答。")
                emit_stream_event(run.id, "answer.started", {"mode": "assistant_answer"})
                stream_started = True
                db.session.commit()
                pending = ""

                def on_answer_delta(delta: str) -> None:
                    nonlocal pending, stream_emitted
                    pending += delta
                    if len(pending) < 36:
                        return
                    emit_stream_event(run.id, "answer.delta", {"delta": pending})
                    pending = ""
                    stream_emitted = True
                    db.session.commit()

                answer_messages = [
                    {"role": "system", "content": ASSISTANT_ANSWER_SYSTEM},
                    {"role": "system", "content": PLATFORM_INVARIANTS},
                    {"role": "system", "content": "实时平台上下文：" + json_dumps(resource_context)},
                    {"role": "system", "content": "可引用知识：" + json_dumps(knowledge_context)},
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": "已校验决策：" + completion.raw_text},
                ]
                try:
                    streamed, stream_usage = provider.complete_text_stream(
                        model=model.model_id, messages=answer_messages, max_tokens=1200,
                        on_delta=on_answer_delta,
                    )
                    _update_usage(run, stream_usage)
                    _record_run_provider_call(run, model, "assistant_answer_stream", stream_usage, "success")
                    if pending:
                        emit_stream_event(run.id, "answer.delta", {"delta": pending})
                        stream_emitted = True
                        pending = ""
                        db.session.commit()
                    streamed_rendered, streamed_cited = _validated_answer(
                        streamed.strip(), resource_context, allowed_knowledge
                    )
                    if streamed_rendered:
                        answer = streamed_rendered
                        cited = streamed_cited
                        valid = True
                except Exception as stream_exc:
                    stream_usage = getattr(stream_exc, "usage", None)
                    if stream_usage is not None:
                        _update_usage(run, stream_usage)
                        _record_run_provider_call(
                            run, model, "assistant_answer_stream", stream_usage, "error",
                            "AI_ASSISTANT_STREAM_FAILED",
                        )

            structured: dict = {"type": "assistant_answer", "intent": decision.intent, "prompt_revision": PROMPT_REVISION}
            client_action = None
            proposed_tool = None
            if decision.intent == "navigate":
                client_action = resolve_navigation(decision.navigation_target, decision.navigation_params, user)
                if client_action:
                    client_action["auto"] = _explicit_navigation(prompt)
                    structured["client_action"] = client_action
            elif decision.intent == "analysis_handoff":
                handoff = decision.handoff_prompt or prompt
                client_action = resolve_navigation("ai_analysis", {"prompt": handoff}, user)
                if client_action:
                    client_action.update({"auto": _explicit_navigation(prompt), "handoff_prompt": handoff})
                    structured["client_action"] = client_action
            elif decision.intent == "propose_action" and decision.action:
                args = _merge_page_action_args(decision.action_args, page_context)
                try:
                    canonical, preconditions, impact = normalize_action(decision.action, args, user)
                    proposed_tool = AiToolCall(
                        run_id=run.id, name=decision.action, status="proposed", args_json=json_dumps(canonical),
                        risk_level="write", idempotency_key=idempotency_key(run.id, user.id, decision.action, canonical),
                        expires_at=datetime.utcnow() + timedelta(minutes=10), precondition_json=json_dumps(preconditions),
                    )
                    db.session.add(proposed_tool)
                    db.session.flush()
                    structured["action"] = {
                        "tool_call_id": proposed_tool.id, "name": proposed_tool.name, "args": canonical,
                        "impact": impact, "expires_at": proposed_tool.expires_at.isoformat(), "requires_confirmation": True,
                    }
                    answer = answer + "\n\n该操作尚未执行。请检查操作卡中的参数和影响后确认。"
                except (ValueError, PermissionError) as exc:
                    decision.intent = "need_clarification"
                    structured["intent"] = "need_clarification"
                    structured["action_validation_error"] = str(exc)
                    answer = f"当前不能提交这个操作：{str(exc)} 请调整目标资源或参数后重试。"

            output = AiMessage(conversation_id=run.conversation_id, role="assistant", content=answer,
                               structured_json=json_dumps(structured))
            db.session.add(output)
            db.session.flush()
            run.output_message_id = output.id
            run.intent = decision.intent
            run.prompt_revision = PROMPT_REVISION
            run.summary_status = "model" if valid else "fallback"
            run.result_json = json_dumps({"assistant": structured, "knowledge_hits": hits, "summary": {"summary": answer}})
            selected_hits = [row for row in hits if row["key"] in cited]
            _persist_citations(output, selected_hits)
            if not stream_started:
                emit_stream_event(run.id, "answer.started", {"message_id": output.id, "mode": "assistant_answer"})
            if not stream_emitted:
                for chunk in _text_chunks(answer):
                    emit_stream_event(run.id, "answer.delta", {"message_id": output.id, "delta": chunk})
            emit_stream_event(run.id, "answer.replace", {"message_id": output.id, "content": answer, "structured": structured})
            if client_action:
                event = "assistant.handoff" if decision.intent == "analysis_handoff" else "ui.navigate"
                emit_stream_event(run.id, event, client_action)
            if proposed_tool:
                run.status = "awaiting_confirmation"
                run.progress = 50
                set_run_phase(run, "confirmation", "安全操作草案等待你的确认。")
                emit_stream_event(run.id, "action.proposed", structured["action"])
                record_audit("ai.action_proposed", actor=user, resource_type="ai_tool_call",
                             resource_id=proposed_tool.id, details={"tool": proposed_tool.name})
            else:
                run.status = "success"
                run.progress = 100
                run.completed_at = datetime.utcnow()
                set_run_phase(run, "planning", "需求理解完成。", state="done")
                set_run_phase(run, "answer", "中文回答已就绪。", state="done")
                emit_stream_event(run.id, "answer.completed", {"status": run.summary_status})
                emit_stream_event(run.id, "run.completed", {"status": "success"})
            record_audit("ai.assistant_completed", actor=user, resource_type="ai_run", resource_id=run.id,
                         details={"intent": decision.intent, "model_config_id": model.id})
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            run = db.session.get(AiRun, run_id)
            if run:
                _fail_run(run, "AI_ASSISTANT_FAILED", str(exc))


def assistant_bootstrap(user: User) -> dict:
    return {
        "routes": [{"name": name, "path": row["path"], "params": sorted(row["params"])} for name, row in ROUTE_REGISTRY.items()],
        "page_context_policy": {"max_chars": 2000, "resource_keys": sorted(_ALLOWED_RESOURCE_KEYS)},
        "conversation_kind": "assistant",
        "prompt_revision": PROMPT_REVISION,
    }
