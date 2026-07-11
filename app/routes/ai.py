"""AI configuration, conversation, planning, and execution JSON API."""
from __future__ import annotations

from datetime import datetime
import json
import time

from flask import Blueprint, Response, current_app, jsonify, request, send_file, stream_with_context
from flask_login import current_user, login_required

from app.ai.registry import default_base_url, provider_catalog, provider_definition
from app.ai.knowledge import (
    can_manage_document,
    can_view_document,
    create_uploaded_document,
    delete_document,
    document_to_dict,
    ensure_builtin_knowledge,
    retrieve_knowledge,
    submit_document_processing,
    visible_documents,
)
from app.ai.schemas import AnalysisPlan, SearchPlan
from app.ai.security import (
    credential_store_status,
    encrypt_api_key,
    mask_api_key,
    sanitize_provider_error,
    validate_base_url,
)
from app.ai.tools import tool_catalog
from app.ai.assistant import assistant_bootstrap, sanitize_page_context, submit_assistant
from app.ai.service import (
    apply_plan,
    conversation_to_dict,
    ensure_one_default_model,
    ensure_user_can_start_run,
    get_ai_settings,
    json_dumps,
    json_loads,
    model_to_dict,
    provider_to_dict,
    run_to_dict,
    set_run_phase,
    settings_to_dict,
    submit_execution,
    submit_planning,
    test_model_connection,
    usage_summary,
    visible_models_query,
)
from app.extensions import db
from app.models import (
    AiConversation,
    AiMessage,
    AiModelConfig,
    AiProviderConfig,
    AiRun,
    AiToolCall,
    Dataset,
    KnowledgeDocument,
    Task,
)
from app.services.access_service import is_admin
from app.services.audit_service import record_audit


ai_bp = Blueprint("ai_api", __name__, url_prefix="/api/ai")


def _error(message: str, status: int = 400, code: str = "AI_BAD_REQUEST"):
    return jsonify(ok=False, message=message, error_code=code), status


def _json() -> dict:
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def _admin_required():
    if not is_admin():
        return _error("仅管理员可以管理 AI 配置。", 403, "AI_ADMIN_REQUIRED")
    return None


def _owned_conversation(conversation_id: int):
    return AiConversation.query.filter_by(id=conversation_id, user_id=current_user.id).first()


def _owned_run(run_id: int):
    return AiRun.query.filter_by(id=run_id, user_id=current_user.id).first()


@ai_bp.route("/catalog", methods=["GET"])
@login_required
def catalog():
    return jsonify(ok=True, providers=provider_catalog())


@ai_bp.route("/capabilities", methods=["GET"])
@login_required
def capabilities():
    return jsonify(ok=True, tools=tool_catalog(), **assistant_bootstrap(current_user))


@ai_bp.route("/assistant/bootstrap", methods=["GET"])
@login_required
def assistant_bootstrap_api():
    return jsonify(ok=True, **assistant_bootstrap(current_user), tools=tool_catalog())


@ai_bp.route("/models", methods=["GET"])
@login_required
def models():
    if not get_ai_settings().enabled or not current_user.ai_enabled:
        return jsonify(ok=True, models=[], disabled=True)
    rows = visible_models_query().order_by(AiModelConfig.is_default.desc(), AiModelConfig.display_name.asc()).all()
    return jsonify(ok=True, models=[model_to_dict(row, public=True) for row in rows], disabled=False)


@ai_bp.route("/knowledge/documents", methods=["GET", "POST"])
@login_required
def knowledge_documents():
    if request.method == "GET":
        scope = request.args.get("scope", "").strip()
        dataset_id = request.args.get("dataset_id", type=int)
        rows = visible_documents(current_user)
        if scope:
            rows = [row for row in rows if row.scope == scope]
        if dataset_id:
            rows = [row for row in rows if row.dataset_id == dataset_id]
        return jsonify(ok=True, documents=[document_to_dict(row, current_user) for row in rows])

    file_storage = request.files.get("file")
    if not file_storage:
        return _error("请选择 PDF、Markdown 或 TXT 文件。", 400, "AI_KNOWLEDGE_FILE_REQUIRED")
    scope = request.form.get("scope", "personal").strip()
    dataset = None
    if scope == "dataset":
        dataset_id = request.form.get("dataset_id", type=int)
        dataset = db.session.get(Dataset, dataset_id) if dataset_id else None
    try:
        document = create_uploaded_document(
            file_storage=file_storage,
            scope=scope,
            title=request.form.get("title", "").strip(),
            description=request.form.get("description", "").strip(),
            user=current_user,
            dataset=dataset,
        )
        record_audit(
            "ai.knowledge_created", resource_type="knowledge_document", resource_id=document.id,
            dataset_id=document.dataset_id, details={"scope": document.scope},
        )
        db.session.commit()
        submit_document_processing(current_app._get_current_object(), document.id)
        return jsonify(ok=True, document=document_to_dict(document, current_user)), 202
    except PermissionError as exc:
        return _error(str(exc), 403, "AI_KNOWLEDGE_FORBIDDEN")
    except Exception as exc:
        db.session.rollback()
        return _error(str(exc), 400, "AI_KNOWLEDGE_INVALID")


@ai_bp.route("/knowledge/documents/<int:document_id>", methods=["GET", "PATCH", "DELETE"])
@login_required
def knowledge_document_detail(document_id: int):
    document = db.session.get(KnowledgeDocument, document_id)
    if not document or not can_view_document(document, current_user):
        return _error("知识文档不存在。", 404, "AI_KNOWLEDGE_NOT_FOUND")
    if request.method == "GET":
        return jsonify(ok=True, document=document_to_dict(document, current_user))
    if not can_manage_document(document, current_user):
        return _error("没有权限维护该知识文档。", 403, "AI_KNOWLEDGE_FORBIDDEN")
    if request.method == "DELETE":
        dataset_id = document.dataset_id
        scope = document.scope
        delete_document(document)
        record_audit(
            "ai.knowledge_deleted", resource_type="knowledge_document", resource_id=document_id,
            dataset_id=dataset_id, details={"scope": scope},
        )
        db.session.commit()
        return jsonify(ok=True)
    payload = _json()
    if "title" in payload:
        title = str(payload["title"] or "").strip()
        if not title:
            return _error("文档标题不能为空。", 400, "AI_KNOWLEDGE_INVALID")
        document.title = title[:300]
    if "description" in payload:
        document.description = str(payload["description"] or "")[:2000]
    db.session.commit()
    return jsonify(ok=True, document=document_to_dict(document, current_user))


@ai_bp.route("/knowledge/documents/<int:document_id>/file", methods=["GET"])
@login_required
def knowledge_document_file(document_id: int):
    document = db.session.get(KnowledgeDocument, document_id)
    if not document or not can_view_document(document, current_user) or not document.stored_path:
        return _error("知识文档不存在。", 404, "AI_KNOWLEDGE_NOT_FOUND")
    return send_file(
        document.stored_path,
        as_attachment=True,
        download_name=document.original_filename or f"knowledge-{document.id}",
    )


@ai_bp.route("/knowledge/documents/<int:document_id>/reindex", methods=["POST"])
@login_required
def knowledge_document_reindex(document_id: int):
    document = db.session.get(KnowledgeDocument, document_id)
    if not document or not can_manage_document(document, current_user):
        return _error("知识文档不存在或无权维护。", 404, "AI_KNOWLEDGE_NOT_FOUND")
    document.status = "pending"
    document.error_message = None
    db.session.commit()
    submit_document_processing(current_app._get_current_object(), document.id)
    return jsonify(ok=True, document=document_to_dict(document, current_user)), 202


@ai_bp.route("/knowledge/search/preview", methods=["GET"])
@login_required
def knowledge_search_preview():
    query = request.args.get("q", "").strip()
    if not query:
        return _error("请输入预览检索词。", 400, "AI_KNOWLEDGE_QUERY_REQUIRED")
    scopes = [item for item in request.args.get("scopes", "platform,dataset,personal").split(",") if item]
    dataset_ids = [int(item) for item in request.args.getlist("dataset_id") if str(item).isdigit()]
    hits = retrieve_knowledge(query, user=current_user, scopes=scopes, dataset_ids=dataset_ids)
    db.session.commit()
    return jsonify(ok=True, hits=[{key: value for key, value in hit.items() if key != "content"} for hit in hits])


@ai_bp.route("/knowledge/builtin/sync", methods=["POST"])
@login_required
def knowledge_builtin_sync():
    denied = _admin_required()
    if denied:
        return denied
    ensure_builtin_knowledge()
    rows = KnowledgeDocument.query.filter_by(source_type="builtin").order_by(KnowledgeDocument.title.asc()).all()
    record_audit("ai.knowledge_builtin_synced", resource_type="knowledge_document")
    db.session.commit()
    return jsonify(ok=True, documents=[document_to_dict(row, current_user) for row in rows])


@ai_bp.route("/conversations", methods=["GET", "POST"])
@login_required
def conversations():
    requested_kind = request.args.get("kind", "").strip()
    if requested_kind and requested_kind not in {"analysis", "assistant"}:
        return _error("会话类型无效。", 400, "AI_CONVERSATION_KIND_INVALID")
    if request.method == "POST":
        payload = _json()
        kind = str(payload.get("kind") or requested_kind or "analysis")
        if kind not in {"analysis", "assistant"}:
            return _error("会话类型无效。", 400, "AI_CONVERSATION_KIND_INVALID")
        default_title = "新建全局助手会话" if kind == "assistant" else "新建 AI 分析"
        title = str(payload.get("title") or default_title).strip()[:200] or default_title
        row = AiConversation(user_id=current_user.id, title=title, kind=kind)
        db.session.add(row)
        db.session.commit()
        return jsonify(ok=True, conversation=conversation_to_dict(row)), 201
    query = AiConversation.query.filter_by(user_id=current_user.id)
    if requested_kind == "assistant":
        # The unified assistant also exposes legacy analysis conversations so
        # users do not lose history during the product-surface migration.
        query = query.filter(AiConversation.kind.in_(["assistant", "analysis"]))
    elif requested_kind:
        query = query.filter_by(kind=requested_kind)
    rows = query.order_by(AiConversation.updated_at.desc()).all()
    return jsonify(ok=True, conversations=[conversation_to_dict(row) for row in rows])


@ai_bp.route("/conversations/<int:conversation_id>", methods=["GET", "DELETE"])
@login_required
def conversation_detail(conversation_id: int):
    row = _owned_conversation(conversation_id)
    if not row:
        return _error("AI 会话不存在。", 404, "AI_CONVERSATION_NOT_FOUND")
    if request.method == "DELETE":
        linked_task_ids = [run.search_task_id for run in row.runs if run.search_task_id]
        linked_task_ids.extend(
            tool.task_id for run in row.runs for tool in run.tool_calls if tool.task_id
        )
        db.session.delete(row)
        for task_id in set(linked_task_ids):
            task = db.session.get(Task, task_id)
            if task and task.source == "ai" and task.created_by_id == current_user.id:
                db.session.delete(task)
        db.session.commit()
        return jsonify(ok=True)
    return jsonify(ok=True, conversation=conversation_to_dict(row, detail=True))


@ai_bp.route("/conversations/<int:conversation_id>/messages", methods=["POST"])
@login_required
def create_message(conversation_id: int):
    conversation = _owned_conversation(conversation_id)
    if not conversation:
        return _error("AI 会话不存在。", 404, "AI_CONVERSATION_NOT_FOUND")
    payload = _json()
    assistant_turn = conversation.kind == "assistant" or payload.get("surface") == "assistant"
    if assistant_turn and conversation.kind != "assistant":
        conversation.kind = "assistant"
    content = str(payload.get("content") or "").strip()
    if not content:
        return _error("请输入自然语言检索需求。", 400, "AI_EMPTY_PROMPT")
    try:
        ensure_user_can_start_run(current_user, content)
    except PermissionError as exc:
        return _error(str(exc), 403, "AI_USAGE_FORBIDDEN")
    except RuntimeError as exc:
        return _error(str(exc), 409, "AI_RUN_CONFLICT")
    except ValueError as exc:
        return _error(str(exc), 400, "AI_PROMPT_INVALID")

    model_id = payload.get("model_config_id")
    query = visible_models_query()
    try:
        model = query.filter(AiModelConfig.id == int(model_id)).first() if model_id else query.filter_by(is_default=True).first()
    except (TypeError, ValueError):
        return _error("模型配置 ID 无效。", 400, "AI_MODEL_INVALID")
    if not model:
        return _error("请选择管理员已测试并启用的模型。", 409, "AI_MODEL_UNAVAILABLE")

    message = AiMessage(conversation_id=conversation.id, role="user", content=content)
    db.session.add(message)
    db.session.flush()
    run = AiRun(
        conversation_id=conversation.id,
        user_id=current_user.id,
        model_config_id=model.id,
        input_message_id=message.id,
        status="queued",
        progress=0,
        surface="assistant" if assistant_turn else "analysis",
        page_context_json=json_dumps(sanitize_page_context(payload.get("page_context"), current_user))
        if payload.get("context_enabled", True) and assistant_turn else None,
        plan_json=json_dumps({
            "requested_knowledge_scopes": [
                item for item in (payload.get("knowledge_scopes") or [])
                if item in {"platform", "dataset", "personal"}
            ]
        }) if payload.get("knowledge_scopes") is not None else None,
    )
    db.session.add(run)
    if conversation.title in {"新建 AI 分析", "新建全局助手会话"}:
        conversation.title = content[:40] + ("…" if len(content) > 40 else "")
    conversation.updated_at = datetime.utcnow()
    db.session.flush()
    record_audit(
        "ai.run_created", resource_type="ai_run", resource_id=run.id,
        details={"model_config_id": model.id},
    )
    db.session.commit()
    if assistant_turn:
        submit_assistant(current_app._get_current_object(), run.id)
    else:
        submit_planning(current_app._get_current_object(), run.id)
    return jsonify(ok=True, run=run_to_dict(run)), 202


@ai_bp.route("/runs/<int:run_id>", methods=["GET"])
@login_required
def run_detail(run_id: int):
    row = _owned_run(run_id)
    if not row:
        return _error("AI Run 不存在。", 404, "AI_RUN_NOT_FOUND")
    return jsonify(ok=True, run=run_to_dict(row))


@ai_bp.route("/runs/<int:run_id>/events", methods=["GET"])
@login_required
def run_events(run_id: int):
    row = _owned_run(run_id)
    if not row:
        return _error("AI Run 不存在。", 404, "AI_RUN_NOT_FOUND")
    try:
        after = int(request.headers.get("Last-Event-ID") or request.args.get("after") or 0)
    except ValueError:
        after = 0
    app = current_app._get_current_object()

    @stream_with_context
    def generate():
        from app.ai.streaming import event_payload, stream_is_terminal
        from app.models import AiStreamEvent
        last_id = after
        last_heartbeat = time.monotonic()
        while True:
            db.session.expire_all()
            events = (
                AiStreamEvent.query.filter(
                    AiStreamEvent.run_id == run_id,
                    AiStreamEvent.sequence > last_id,
                ).order_by(AiStreamEvent.sequence.asc()).limit(100).all()
            )
            for event in events:
                last_id = event.sequence
                payload = json.dumps(event_payload(event), ensure_ascii=False, separators=(",", ":"))
                yield f"id: {event.sequence}\nevent: {event.event_type}\ndata: {payload}\n\n"
            current = db.session.get(AiRun, run_id)
            if stream_is_terminal(current) and not events:
                break
            if time.monotonic() - last_heartbeat >= 15:
                yield ": heartbeat\n\n"
                last_heartbeat = time.monotonic()
            time.sleep(0.5)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@ai_bp.route("/runs/<int:run_id>/cancel", methods=["POST"])
@login_required
def cancel_run(run_id: int):
    row = _owned_run(run_id)
    if not row:
        return _error("AI Run 不存在。", 404, "AI_RUN_NOT_FOUND")
    if row.status in {"error", "rejected", "cancelled"} or (
        row.status == "success" and row.summary_status in {"model", "fallback", "not_started"}
    ):
        return jsonify(ok=True, run=run_to_dict(row))
    row.cancel_requested = True
    if row.status in {"queued", "needs_input", "awaiting_confirmation"}:
        from app.ai.service import _cancel_run
        _cancel_run(row)
    db.session.commit()
    return jsonify(ok=True, run=run_to_dict(row)), 202


@ai_bp.route("/runs/<int:run_id>/plan", methods=["PUT"])
@login_required
def update_run_plan(run_id: int):
    row = _owned_run(run_id)
    if not row:
        return _error("AI Run 不存在。", 404, "AI_RUN_NOT_FOUND")
    if row.status not in {"needs_input", "awaiting_confirmation"}:
        return _error("当前状态不能修改检索计划。", 409, "AI_PLAN_NOT_EDITABLE")
    payload = _json()
    existing = json_loads(row.plan_json)
    if isinstance(existing.get("steps"), list):
        candidate = dict(existing)
        candidate.update({
            key: value for key, value in payload.items()
            if key in {"goal", "response_language", "knowledge_scopes", "steps", "expected_outputs"}
        })
        try:
            plan = AnalysisPlan.model_validate(candidate)
            from app.ai.service import apply_analysis_plan
            resolved, valid = apply_analysis_plan(row, plan, current_user)
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            return _error(str(exc), 400, "AI_PLAN_INVALID")
        return jsonify(ok=True, run=run_to_dict(row), valid=valid, plan=resolved)
    editable = {
        key: existing.get(key)
        for key in (
            "intent", "dataset_reference", "query_cell_index", "top_k", "filter_cell_type",
            "index_reference", "index_policy", "analysis_dimensions"
        )
    }
    editable.update({key: value for key, value in payload.items() if key in editable})
    if "dataset_id" in payload:
        editable["dataset_reference"] = payload["dataset_id"]
    if "index_id" in payload:
        editable["index_reference"] = payload["index_id"]
        editable["index_policy"] = "explicit"
    try:
        plan = SearchPlan.model_validate(editable)
        resolved, valid = apply_plan(row, plan, current_user)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return _error(str(exc), 400, "AI_PLAN_INVALID")
    return jsonify(ok=True, run=run_to_dict(row), valid=valid, plan=resolved)


@ai_bp.route("/runs/<int:run_id>/approve", methods=["POST"])
@login_required
def approve_run(run_id: int):
    row = _owned_run(run_id)
    if not row:
        return _error("AI Run 不存在。", 404, "AI_RUN_NOT_FOUND")
    if row.status != "awaiting_confirmation":
        return _error("当前 Run 尚未达到可确认状态。", 409, "AI_RUN_NOT_APPROVABLE")
    if (row.surface or "analysis") == "assistant":
        proposed = next((tool for tool in row.tool_calls if tool.status == "proposed"), None)
        if not proposed:
            return _error("待确认的安全操作不存在。", 409, "AI_TOOL_NOT_PROPOSED")
        return _approve_assistant_tool(proposed)
    tools = [tool for tool in row.tool_calls if tool.status == "proposed"]
    if not tools:
        return _error("待执行工具调用不存在。", 409, "AI_TOOL_NOT_PROPOSED")
    for tool in tools:
        tool.status = "approved"
        tool.approved_by_id = current_user.id
    row.status = "executing"
    row.progress = 50
    set_run_phase(row, "confirmation", "检索计划已确认。", state="done")
    set_run_phase(row, "search", "检索任务正在启动。")
    record_audit(
        "ai.run_approved", resource_type="ai_run", resource_id=row.id,
        dataset_id=json_loads(row.plan_json).get("dataset_id"),
        details={"tools": [tool.name for tool in tools], "model_config_id": row.model_config_id},
    )
    db.session.commit()
    submit_execution(current_app._get_current_object(), row.id)
    return jsonify(ok=True, run=run_to_dict(row)), 202


def _owned_tool_call(tool_call_id: int):
    return (
        AiToolCall.query.join(AiRun, AiRun.id == AiToolCall.run_id)
        .filter(AiToolCall.id == tool_call_id, AiRun.user_id == current_user.id)
        .first()
    )


def _tool_payload(tool: AiToolCall) -> dict:
    return {
        "id": tool.id, "run_id": tool.run_id, "name": tool.name, "status": tool.status,
        "risk_level": tool.risk_level or "read", "args": json_loads(tool.args_json),
        "result": json_loads(tool.result_json, None) if tool.result_json else None,
        "task_id": tool.task_id,
        "expires_at": tool.expires_at.isoformat() if tool.expires_at else None,
        "approved_at": tool.approved_at.isoformat() if tool.approved_at else None,
    }


def _approve_assistant_tool(tool: AiToolCall):
    from app.ai.streaming import emit_stream_event
    from app.services.platform_action_service import execute_action, normalize_action

    run = tool.run
    if tool.status != "proposed" or run.status != "awaiting_confirmation":
        return _error("当前操作不处于可确认状态。", 409, "AI_TOOL_NOT_APPROVABLE")
    if tool.expires_at and tool.expires_at <= datetime.utcnow():
        tool.status = "expired"
        run.status = "rejected"
        run.completed_at = datetime.utcnow()
        emit_stream_event(run.id, "action.status", {"tool_call_id": tool.id, "status": "expired"})
        emit_stream_event(run.id, "run.completed", {"status": "rejected"})
        db.session.commit()
        return _error("操作草案已过期，请重新发起。", 409, "AI_TOOL_EXPIRED")
    args = json_loads(tool.args_json)
    try:
        canonical, current_preconditions, _ = normalize_action(tool.name, args, current_user)
        if current_preconditions != json_loads(tool.precondition_json, {}):
            raise ValueError("目标资源状态已经变化，请重新生成操作草案。")
        tool.status = "running"
        tool.approved_by_id = current_user.id
        tool.approved_at = datetime.utcnow()
        run.status = "executing"
        set_run_phase(run, "confirmation", "安全操作已确认。", state="done")
        set_run_phase(run, "search", "正在提交平台任务。")
        emit_stream_event(run.id, "action.status", {"tool_call_id": tool.id, "status": "running"})
        db.session.commit()
        result = execute_action(tool.name, canonical, current_user, current_app._get_current_object())
        tool = db.session.get(AiToolCall, tool.id)
        run = db.session.get(AiRun, run.id)
        tool.status = "success"
        tool.result_json = json_dumps(result)
        tool.task_id = result.get("task_id")
        run.status = "success"
        run.progress = 100
        run.completed_at = datetime.utcnow()
        run.summary_status = run.summary_status if run.summary_status in {"model", "fallback"} else "model"
        set_run_phase(run, "search", "平台任务已成功提交。", state="done")
        set_run_phase(run, "answer", "操作结果已就绪。", state="done")
        if run.output_message:
            run.output_message.content += "\n\n操作已确认并成功提交。" + (
                f"后台 Task #{result['task_id']} 可在任务中心查看。" if result.get("task_id") else ""
            )
            structured = json_loads(run.output_message.structured_json, {})
            structured["action_result"] = result
            run.output_message.structured_json = json_dumps(structured)
        emit_stream_event(run.id, "action.status", {
            "tool_call_id": tool.id, "status": "success", "result": result,
        })
        if isinstance(result.get("navigation"), dict):
            emit_stream_event(run.id, "ui.navigate", result["navigation"])
        emit_stream_event(run.id, "answer.replace", {
            "message_id": run.output_message_id,
            "content": run.output_message.content if run.output_message else "操作已提交。",
        })
        emit_stream_event(run.id, "run.completed", {"status": "success"})
        record_audit("ai.action_executed", resource_type="ai_tool_call", resource_id=tool.id,
                     details={"tool": tool.name, "task_id": tool.task_id})
        db.session.commit()
        return jsonify(ok=True, tool_call=_tool_payload(tool), run=run_to_dict(run)), 202
    except PermissionError as exc:
        db.session.rollback()
        return _error(str(exc), 403, "AI_ACTION_FORBIDDEN")
    except Exception as exc:
        db.session.rollback()
        tool = db.session.get(AiToolCall, tool.id)
        run = db.session.get(AiRun, run.id)
        if tool:
            tool.status = "error"
            tool.result_json = json_dumps({"error": str(exc)[:300]})
        if run:
            run.status = "error"
            run.error_code = "AI_ACTION_FAILED"
            run.error_message = str(exc)[:500]
            run.completed_at = datetime.utcnow()
            emit_stream_event(run.id, "action.status", {"tool_call_id": tool.id, "status": "error"})
            emit_stream_event(run.id, "error", {"error_code": run.error_code, "message": run.error_message})
            emit_stream_event(run.id, "run.completed", {"status": "error"})
        db.session.commit()
        return _error(str(exc), 400, "AI_ACTION_FAILED")


@ai_bp.route("/tool-calls/<int:tool_call_id>", methods=["GET"])
@login_required
def tool_call_detail(tool_call_id: int):
    tool = _owned_tool_call(tool_call_id)
    if not tool:
        return _error("工具调用不存在。", 404, "AI_TOOL_NOT_FOUND")
    return jsonify(ok=True, tool_call=_tool_payload(tool))


@ai_bp.route("/tool-calls/<int:tool_call_id>/approve", methods=["POST"])
@login_required
def approve_tool_call(tool_call_id: int):
    tool = _owned_tool_call(tool_call_id)
    if not tool:
        return _error("工具调用不存在。", 404, "AI_TOOL_NOT_FOUND")
    return _approve_assistant_tool(tool)


@ai_bp.route("/tool-calls/<int:tool_call_id>/reject", methods=["POST"])
@login_required
def reject_tool_call(tool_call_id: int):
    from app.ai.streaming import emit_stream_event
    tool = _owned_tool_call(tool_call_id)
    if not tool:
        return _error("工具调用不存在。", 404, "AI_TOOL_NOT_FOUND")
    if tool.status != "proposed":
        return _error("当前操作不能拒绝。", 409, "AI_TOOL_NOT_REJECTABLE")
    tool.status = "rejected"
    run = tool.run
    run.status = "rejected"
    run.progress = 100
    run.completed_at = datetime.utcnow()
    emit_stream_event(run.id, "action.status", {"tool_call_id": tool.id, "status": "rejected"})
    emit_stream_event(run.id, "run.completed", {"status": "rejected"})
    record_audit("ai.action_rejected", resource_type="ai_tool_call", resource_id=tool.id,
                 details={"tool": tool.name})
    db.session.commit()
    return jsonify(ok=True, tool_call=_tool_payload(tool), run=run_to_dict(run))


@ai_bp.route("/runs/<int:run_id>/reject", methods=["POST"])
@login_required
def reject_run(run_id: int):
    row = _owned_run(run_id)
    if not row:
        return _error("AI Run 不存在。", 404, "AI_RUN_NOT_FOUND")
    if row.status not in {"needs_input", "awaiting_confirmation"}:
        return _error("当前 Run 不能拒绝。", 409, "AI_RUN_NOT_REJECTABLE")
    row.status = "rejected"
    row.progress = 100
    row.completed_at = datetime.utcnow()
    for tool in row.tool_calls:
        if tool.status == "proposed":
            tool.status = "rejected"
    set_run_phase(row, "confirmation", "用户已拒绝本次检索计划。", state="done")
    set_run_phase(row, "search", "未执行 ANN 检索。", state="skipped")
    set_run_phase(row, "answer", "本轮已取消。", state="skipped")
    db.session.add(AiMessage(
        conversation_id=row.conversation_id,
        role="assistant",
        content="已取消本次检索计划，未调用平台检索功能。",
    ))
    record_audit(
        "ai.run_rejected", resource_type="ai_run", resource_id=row.id,
        details={"model_config_id": row.model_config_id},
    )
    db.session.commit()
    return jsonify(ok=True, run=run_to_dict(row))


@ai_bp.route("/admin/settings", methods=["GET", "PATCH"])
@login_required
def admin_settings():
    denied = _admin_required()
    if denied:
        return denied
    row = get_ai_settings()
    if request.method == "PATCH":
        payload = _json()
        if "enabled" in payload:
            row.enabled = bool(payload["enabled"])
        for key, low, high in (
            ("daily_request_limit", 0, 100000),
            ("max_concurrent_runs", 1, 10),
            ("max_prompt_chars", 100, 50000),
            ("default_knowledge_top_k", 1, 8),
            ("max_knowledge_file_mb", 1, 100),
        ):
            if key in payload:
                value = int(payload[key])
                if value < low or value > high:
                    return _error(f"{key} 超出允许范围。", 400, "AI_SETTING_INVALID")
                setattr(row, key, value)
        if "rag_enabled" in payload:
            row.rag_enabled = bool(payload["rag_enabled"])
        record_audit("ai.settings_updated", resource_type="ai_settings", resource_id=1)
        db.session.commit()
    return jsonify(
        ok=True,
        settings=settings_to_dict(row),
        credential_store=credential_store_status(),
        catalog=provider_catalog(),
    )


@ai_bp.route("/admin/providers", methods=["GET", "POST"])
@login_required
def admin_providers():
    denied = _admin_required()
    if denied:
        return denied
    if request.method == "GET":
        rows = AiProviderConfig.query.order_by(AiProviderConfig.created_at.desc()).all()
        return jsonify(ok=True, providers=[provider_to_dict(row) for row in rows])
    payload = _json()
    try:
        provider_key = str(payload.get("provider") or "").strip().lower()
        provider_definition(provider_key)
        api_key = str(payload.get("api_key") or "").strip()
        base_url = validate_base_url(str(payload.get("base_url") or default_base_url(provider_key)))
        timeout = int(payload.get("timeout_seconds", 180))
        if timeout < 15 or timeout > 600:
            raise ValueError("超时时间应位于 15 到 600 秒。")
        row = AiProviderConfig(
            provider=provider_key,
            name=str(payload.get("name") or provider_definition(provider_key)["label"]).strip()[:120],
            base_url=base_url,
            api_key_ciphertext=encrypt_api_key(api_key),
            api_key_hint=mask_api_key(api_key),
            enabled=bool(payload.get("enabled", True)),
            timeout_seconds=timeout,
            created_by_id=current_user.id,
        )
        db.session.add(row)
        db.session.flush()
        record_audit(
            "ai.provider_created", resource_type="ai_provider", resource_id=row.id,
            details={"provider": provider_key},
        )
        db.session.commit()
        return jsonify(ok=True, provider=provider_to_dict(row)), 201
    except Exception as exc:
        db.session.rollback()
        return _error(sanitize_provider_error(exc), 400, "AI_PROVIDER_INVALID")


@ai_bp.route("/admin/providers/<int:provider_id>", methods=["PATCH", "DELETE"])
@login_required
def admin_provider_detail(provider_id: int):
    denied = _admin_required()
    if denied:
        return denied
    row = db.session.get(AiProviderConfig, provider_id)
    if not row:
        return _error("供应商配置不存在。", 404, "AI_PROVIDER_NOT_FOUND")
    if request.method == "DELETE":
        model_ids = [item.id for item in row.model_configs]
        if model_ids and AiRun.query.filter(AiRun.model_config_id.in_(model_ids)).count():
            return _error("该配置已有历史 Run 引用，请禁用而不是删除。", 409, "AI_PROVIDER_IN_USE")
        db.session.delete(row)
        record_audit(
            "ai.provider_deleted", resource_type="ai_provider", resource_id=provider_id,
            details={"provider": row.provider},
        )
        db.session.commit()
        return jsonify(ok=True)
    payload = _json()
    reset_tests = False
    try:
        if "name" in payload:
            row.name = str(payload["name"]).strip()[:120]
        if "enabled" in payload:
            row.enabled = bool(payload["enabled"])
        if "timeout_seconds" in payload:
            timeout = int(payload["timeout_seconds"])
            if timeout < 15 or timeout > 600:
                raise ValueError("超时时间应位于 15 到 600 秒。")
            row.timeout_seconds = timeout
        if "base_url" in payload and str(payload["base_url"]).strip() != row.base_url:
            row.base_url = validate_base_url(str(payload["base_url"]))
            reset_tests = True
        if str(payload.get("api_key") or "").strip():
            key = str(payload["api_key"]).strip()
            row.api_key_ciphertext = encrypt_api_key(key)
            row.api_key_hint = mask_api_key(key)
            reset_tests = True
            event = "ai.provider_key_rotated"
        else:
            event = "ai.provider_updated"
        if reset_tests:
            row.last_test_status = "untested"
            row.last_test_message = None
            for model in row.model_configs:
                model.enabled = False
                model.is_default = False
                model.last_test_status = "untested"
                model.last_test_message = None
        record_audit(
            event, resource_type="ai_provider", resource_id=row.id,
            details={"provider": row.provider},
        )
        ensure_one_default_model()
        db.session.commit()
        return jsonify(ok=True, provider=provider_to_dict(row))
    except Exception as exc:
        db.session.rollback()
        return _error(sanitize_provider_error(exc), 400, "AI_PROVIDER_INVALID")


@ai_bp.route("/admin/models", methods=["GET", "POST"])
@login_required
def admin_models():
    denied = _admin_required()
    if denied:
        return denied
    if request.method == "GET":
        rows = AiModelConfig.query.order_by(AiModelConfig.created_at.desc()).all()
        return jsonify(ok=True, models=[model_to_dict(row) for row in rows])
    payload = _json()
    provider = db.session.get(AiProviderConfig, int(payload.get("provider_config_id") or 0))
    if not provider:
        return _error("供应商配置不存在。", 404, "AI_PROVIDER_NOT_FOUND")
    model_id = str(payload.get("model_id") or "").strip()
    capability = str(payload.get("capability") or "chat").strip()
    if capability not in {"chat", "embedding"}:
        return _error("模型能力必须是 chat 或 embedding。", 400, "AI_MODEL_INVALID")
    if not model_id or len(model_id) > 200:
        return _error("请输入有效模型 ID。", 400, "AI_MODEL_INVALID")
    row = AiModelConfig(
        provider_config_id=provider.id,
        model_id=model_id,
        display_name=str(payload.get("display_name") or model_id).strip()[:200],
        capability=capability,
    )
    try:
        db.session.add(row)
        db.session.flush()
        record_audit(
            "ai.model_created", resource_type="ai_model", resource_id=row.id,
            details={"provider_config_id": provider.id, "model_id": model_id},
        )
        db.session.commit()
        return jsonify(ok=True, model=model_to_dict(row)), 201
    except Exception:
        db.session.rollback()
        return _error("同一供应商下不能重复添加相同模型 ID。", 409, "AI_MODEL_DUPLICATE")


@ai_bp.route("/admin/models/<int:model_id>", methods=["PATCH", "DELETE"])
@login_required
def admin_model_detail(model_id: int):
    denied = _admin_required()
    if denied:
        return denied
    row = db.session.get(AiModelConfig, model_id)
    if not row:
        return _error("模型配置不存在。", 404, "AI_MODEL_NOT_FOUND")
    if request.method == "DELETE":
        if AiRun.query.filter_by(model_config_id=row.id).count():
            return _error("该模型已有历史 Run 引用，请禁用而不是删除。", 409, "AI_MODEL_IN_USE")
        db.session.delete(row)
        record_audit("ai.model_deleted", resource_type="ai_model", resource_id=row.id)
        ensure_one_default_model()
        db.session.commit()
        return jsonify(ok=True)
    payload = _json()
    if "display_name" in payload:
        row.display_name = str(payload["display_name"]).strip()[:200]
    if "model_id" in payload and str(payload["model_id"]).strip() != row.model_id:
        row.model_id = str(payload["model_id"]).strip()[:200]
        row.enabled = False
        row.is_default = False
        row.last_test_status = "untested"
        row.last_test_message = None
        row.embedding_dimensions = None
    if "enabled" in payload:
        enabling = bool(payload["enabled"])
        if enabling and (row.last_test_status != "success" or not row.provider_config.enabled):
            return _error("模型必须测试成功且供应商已启用。", 409, "AI_MODEL_NOT_TESTED")
        row.enabled = enabling
        if not enabling:
            row.is_default = False
    if bool(payload.get("is_default")):
        if not row.enabled:
            return _error("只有已启用模型可以设为默认。", 409, "AI_MODEL_NOT_ENABLED")
        AiModelConfig.query.filter_by(capability=row.capability).update({AiModelConfig.is_default: False})
        row.is_default = True
    ensure_one_default_model()
    reindex_ids = []
    if row.capability == "embedding" and row.enabled and row.is_default and (
        "enabled" in payload or bool(payload.get("is_default"))
    ):
        documents = KnowledgeDocument.query.filter(
            KnowledgeDocument.status.in_(["ready", "degraded"])
        ).all()
        for document in documents:
            document.status = "degraded"
            document.semantic_status = "pending"
            reindex_ids.append(document.id)
    record_audit(
        "ai.model_updated", resource_type="ai_model", resource_id=row.id,
        details={"enabled": bool(row.enabled), "is_default": bool(row.is_default)},
    )
    db.session.commit()
    for document_id in reindex_ids:
        submit_document_processing(current_app._get_current_object(), document_id)
    return jsonify(ok=True, model=model_to_dict(row))


@ai_bp.route("/admin/models/<int:model_id>/test", methods=["POST"])
@login_required
def admin_test_model(model_id: int):
    denied = _admin_required()
    if denied:
        return denied
    row = db.session.get(AiModelConfig, model_id)
    if not row:
        return _error("模型配置不存在。", 404, "AI_MODEL_NOT_FOUND")
    try:
        usage = test_model_connection(row)
        row.last_test_status = "success"
        row.last_test_message = "连接测试成功。"
        row.last_tested_at = datetime.utcnow()
        row.provider_config.last_test_status = "success"
        row.provider_config.last_test_message = "至少一个模型连接测试成功。"
        row.provider_config.last_tested_at = datetime.utcnow()
        record_audit(
            "ai.model_tested", resource_type="ai_model", resource_id=row.id,
            details={"success": True, "latency_ms": round(usage.latency_ms, 2)},
        )
        db.session.commit()
        return jsonify(ok=True, model=model_to_dict(row), latency_ms=usage.latency_ms)
    except Exception as exc:
        message = sanitize_provider_error(exc)
        row.enabled = False
        row.is_default = False
        row.last_test_status = "error"
        row.last_test_message = message
        row.last_tested_at = datetime.utcnow()
        row.provider_config.last_test_status = "error"
        row.provider_config.last_test_message = message
        row.provider_config.last_tested_at = datetime.utcnow()
        ensure_one_default_model()
        record_audit(
            "ai.model_tested", resource_type="ai_model", resource_id=row.id,
            details={"success": False},
        )
        db.session.commit()
        return _error(f"连接测试失败：{message}", 400, "AI_MODEL_TEST_FAILED")


@ai_bp.route("/admin/usage", methods=["GET"])
@login_required
def admin_usage():
    denied = _admin_required()
    if denied:
        return denied
    return jsonify(ok=True, usage=usage_summary())
