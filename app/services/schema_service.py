"""轻量 SQLite 结构补齐，用于兼容课程项目中的既有本地数据库。"""
import json

from sqlalchemy import inspect, text
from app.extensions import db


def ensure_sqlite_schema():
    from app import models as _models  # noqa: F401 - ensure model metadata is registered

    engine = db.engine
    if not engine.url.drivername.startswith("sqlite"):
        return

    inspector = inspect(engine)
    if not inspector.has_table("datasets"):
        return

    for table_name in [
        "dataset_permissions",
        "audit_logs",
        "joint_indexes",
        "joint_index_datasets",
        "joint_query_logs",
        "index_experiments",
        "index_experiment_runs",
        "index_evaluations",
        "ai_system_settings",
        "ai_provider_configs",
        "ai_model_configs",
        "ai_conversations",
        "ai_messages",
        "ai_runs",
        "ai_tool_calls",
        "knowledge_documents",
        "knowledge_chunks",
        "ai_citations",
        "ai_stream_events",
        "ai_provider_calls",
    ]:
        if not inspector.has_table(table_name):
            db.Model.metadata.tables[table_name].create(bind=engine, checkfirst=True)

    # Refresh table/column discovery after creating compatibility tables.
    inspector = inspect(engine)

    existing = {col["name"] for col in inspector.get_columns("datasets")}
    statements = []
    if "owner_id" not in existing:
        statements.append("ALTER TABLE datasets ADD COLUMN owner_id INTEGER")
    if "visibility" not in existing:
        statements.append("ALTER TABLE datasets ADD COLUMN visibility VARCHAR(20) DEFAULT 'private'")

    user_existing = {col["name"] for col in inspector.get_columns("users")} if inspector.has_table("users") else set()
    if "is_enabled" not in user_existing:
        statements.append("ALTER TABLE users ADD COLUMN is_enabled BOOLEAN DEFAULT 1 NOT NULL")
    if "ai_enabled" not in user_existing:
        statements.append("ALTER TABLE users ADD COLUMN ai_enabled BOOLEAN DEFAULT 1 NOT NULL")
    if "ai_daily_limit_override" not in user_existing:
        statements.append("ALTER TABLE users ADD COLUMN ai_daily_limit_override INTEGER")

    task_existing = {col["name"] for col in inspector.get_columns("tasks")} if inspector.has_table("tasks") else set()
    if "created_by_id" not in task_existing:
        statements.append("ALTER TABLE tasks ADD COLUMN created_by_id INTEGER")
    if "request_json" not in task_existing:
        statements.append("ALTER TABLE tasks ADD COLUMN request_json TEXT")
    if "source" not in task_existing:
        statements.append("ALTER TABLE tasks ADD COLUMN source VARCHAR(30) DEFAULT 'query_lab' NOT NULL")
    if "history_hidden" not in task_existing:
        statements.append("ALTER TABLE tasks ADD COLUMN history_hidden BOOLEAN DEFAULT 0 NOT NULL")

    ai_run_existing = (
        {col["name"] for col in inspector.get_columns("ai_runs")}
        if inspector.has_table("ai_runs") else set()
    )
    for column_name, definition in [
        ("output_message_id", "INTEGER"),
        ("context_run_id", "INTEGER"),
        ("search_task_id", "INTEGER"),
        ("intent", "VARCHAR(40) DEFAULT 'single_cell_search' NOT NULL"),
        ("summary_status", "VARCHAR(30) DEFAULT 'not_started' NOT NULL"),
        ("summary_message", "VARCHAR(500)"),
        ("phase_json", "TEXT"),
        ("response_language", "VARCHAR(20) DEFAULT 'zh-CN' NOT NULL"),
        ("cancel_requested", "BOOLEAN DEFAULT 0 NOT NULL"),
    ]:
        if column_name not in ai_run_existing:
            statements.append(f"ALTER TABLE ai_runs ADD COLUMN {column_name} {definition}")

    ai_settings_existing = (
        {col["name"] for col in inspector.get_columns("ai_system_settings")}
        if inspector.has_table("ai_system_settings") else set()
    )
    for column_name, definition in [
        ("rag_enabled", "BOOLEAN DEFAULT 1 NOT NULL"),
        ("default_knowledge_top_k", "INTEGER DEFAULT 8 NOT NULL"),
        ("max_knowledge_file_mb", "INTEGER DEFAULT 25 NOT NULL"),
    ]:
        if column_name not in ai_settings_existing:
            statements.append(f"ALTER TABLE ai_system_settings ADD COLUMN {column_name} {definition}")

    ai_model_existing = (
        {col["name"] for col in inspector.get_columns("ai_model_configs")}
        if inspector.has_table("ai_model_configs") else set()
    )
    if "capability" not in ai_model_existing:
        statements.append("ALTER TABLE ai_model_configs ADD COLUMN capability VARCHAR(20) DEFAULT 'chat' NOT NULL")
    if "embedding_dimensions" not in ai_model_existing:
        statements.append("ALTER TABLE ai_model_configs ADD COLUMN embedding_dimensions INTEGER")

    ai_tool_existing = (
        {col["name"] for col in inspector.get_columns("ai_tool_calls")}
        if inspector.has_table("ai_tool_calls") else set()
    )
    if "task_id" not in ai_tool_existing:
        statements.append("ALTER TABLE ai_tool_calls ADD COLUMN task_id INTEGER")
    if "order_index" not in ai_tool_existing:
        statements.append("ALTER TABLE ai_tool_calls ADD COLUMN order_index INTEGER DEFAULT 0 NOT NULL")

    query_log_existing = (
        {col["name"] for col in inspector.get_columns("query_logs")}
        if inspector.has_table("query_logs") else set()
    )
    if "user_id" not in query_log_existing:
        statements.append("ALTER TABLE query_logs ADD COLUMN user_id INTEGER")

    joint_query_log_existing = (
        {col["name"] for col in inspector.get_columns("joint_query_logs")}
        if inspector.has_table("joint_query_logs") else set()
    )
    if "user_id" not in joint_query_log_existing:
        statements.append("ALTER TABLE joint_query_logs ADD COLUMN user_id INTEGER")

    index_existing = {col["name"] for col in inspector.get_columns("ann_indexes")} if inspector.has_table("ann_indexes") else set()
    if "algorithm" not in index_existing:
        statements.append("ALTER TABLE ann_indexes ADD COLUMN algorithm VARCHAR(60) DEFAULT 'hnswlib_hnsw'")
    if "preprocess_path" not in index_existing:
        statements.append("ALTER TABLE ann_indexes ADD COLUMN preprocess_path VARCHAR(500)")
    if "params_json" not in index_existing:
        statements.append("ALTER TABLE ann_indexes ADD COLUMN params_json TEXT")
    if "index_size_bytes" not in index_existing:
        statements.append("ALTER TABLE ann_indexes ADD COLUMN index_size_bytes INTEGER")
    if "backend_version" not in index_existing:
        statements.append("ALTER TABLE ann_indexes ADD COLUMN backend_version VARCHAR(120)")
    if "error_message" not in index_existing:
        statements.append("ALTER TABLE ann_indexes ADD COLUMN error_message TEXT")
    if "source_experiment_id" not in index_existing:
        statements.append("ALTER TABLE ann_indexes ADD COLUMN source_experiment_id INTEGER")
    if "source_run_id" not in index_existing:
        statements.append("ALTER TABLE ann_indexes ADD COLUMN source_run_id INTEGER")
    if "lifecycle" not in index_existing:
        statements.append("ALTER TABLE ann_indexes ADD COLUMN lifecycle VARCHAR(20) DEFAULT 'active' NOT NULL")
    if "selection_labels" not in index_existing:
        statements.append("ALTER TABLE ann_indexes ADD COLUMN selection_labels VARCHAR(200)")
    if "discarded_at" not in index_existing:
        statements.append("ALTER TABLE ann_indexes ADD COLUMN discarded_at DATETIME")

    experiment_existing = (
        {col["name"] for col in inspector.get_columns("index_experiments")}
        if inspector.has_table("index_experiments")
        else set()
    )
    for column_name, definition in [
        ("created_by_id", "INTEGER"),
        ("seed", "INTEGER DEFAULT 42"),
        ("repetitions", "INTEGER DEFAULT 3"),
        ("warmup_count", "INTEGER DEFAULT 10"),
        ("exact_avg_query_time_ms", "FLOAT"),
        ("exact_p95_query_time_ms", "FLOAT"),
        ("selected_run_ids_json", "TEXT"),
        ("finalized_at", "DATETIME"),
        ("reclaimed_bytes", "INTEGER DEFAULT 0"),
    ]:
        if column_name not in experiment_existing:
            statements.append(f"ALTER TABLE index_experiments ADD COLUMN {column_name} {definition}")

    experiment_run_existing = (
        {col["name"] for col in inspector.get_columns("index_experiment_runs")}
        if inspector.has_table("index_experiment_runs")
        else set()
    )
    if "quality" not in experiment_run_existing:
        statements.append("ALTER TABLE index_experiment_runs ADD COLUMN quality VARCHAR(40)")

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
        conn.execute(text("UPDATE users SET is_enabled = 1 WHERE is_enabled IS NULL"))
        conn.execute(text("UPDATE users SET ai_enabled = 1 WHERE ai_enabled IS NULL"))
        conn.execute(text("UPDATE tasks SET source = 'query_lab' WHERE source IS NULL OR source = ''"))
        conn.execute(text("UPDATE tasks SET history_hidden = 0 WHERE history_hidden IS NULL"))
        if inspect(engine).has_table("ai_runs"):
            conn.execute(text(
                "UPDATE ai_runs SET intent = 'single_cell_search' WHERE intent IS NULL OR intent = ''"
            ))
            conn.execute(text(
                "UPDATE ai_runs SET summary_status = 'not_started' "
                "WHERE summary_status IS NULL OR summary_status = ''"
            ))
            conn.execute(text(
                "UPDATE ai_runs SET response_language = 'zh-CN' "
                "WHERE response_language IS NULL OR response_language = ''"
            ))
            conn.execute(text("UPDATE ai_runs SET cancel_requested = 0 WHERE cancel_requested IS NULL"))
        if inspect(engine).has_table("ai_model_configs"):
            conn.execute(text(
                "UPDATE ai_model_configs SET capability = 'chat' "
                "WHERE capability IS NULL OR capability = ''"
            ))
        if inspect(engine).has_table("ai_tool_calls"):
            conn.execute(text("UPDATE ai_tool_calls SET order_index = 0 WHERE order_index IS NULL"))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_tasks_owner_history "
            "ON tasks (created_by_id, history_hidden, updated_at)"
        ))
        admin_id = conn.execute(text(
            "SELECT id FROM users WHERE role = 'admin' AND is_enabled = 1 ORDER BY id LIMIT 1"
        )).scalar()
        if admin_id is not None:
            conn.execute(
                text("UPDATE datasets SET owner_id = :admin_id WHERE owner_id IS NULL"),
                {"admin_id": admin_id},
            )

    # Keep the singleton settings row available without requiring a separate
    # migration command. This is safe for both fresh and upgraded SQLite DBs.
    if inspect(engine).has_table("ai_system_settings"):
        with engine.begin() as conn:
            exists = conn.execute(text("SELECT id FROM ai_system_settings WHERE id = 1")).scalar()
            if exists is None:
                conn.execute(text(
                    "INSERT INTO ai_system_settings "
                    "(id, enabled, daily_request_limit, max_concurrent_runs, max_prompt_chars, "
                    "rag_enabled, default_knowledge_top_k, max_knowledge_file_mb, created_at, updated_at) "
                    "VALUES (1, 1, 50, 1, 4000, 1, 8, 25, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                ))

    # Older AI runs predate the shared search-task history. Backfill one task
    # per successful run so existing analyses can be opened in Query Lab.
    if inspect(engine).has_table("ai_runs") and inspect(engine).has_table("tasks"):
        from app.models import AiRun, Task

        changed = False
        rows = AiRun.query.filter(
            AiRun.search_task_id.is_(None),
            AiRun.status == "success",
            AiRun.result_json.isnot(None),
        ).all()
        for run in rows:
            try:
                result = json.loads(run.result_json or "{}")
                search = result.get("search")
                plan = json.loads(run.plan_json or "{}")
            except (TypeError, json.JSONDecodeError):
                continue
            if not isinstance(search, dict) or not isinstance(plan, dict):
                continue
            request_data = {
                "mode": "single",
                "dataset_id": plan.get("dataset_id"),
                "index_id": plan.get("index_id"),
                "query_cell_index": plan.get("query_cell_index"),
                "top_k": plan.get("top_k"),
                "filter_cell_type": plan.get("filter_cell_type"),
            }
            task = Task(
                type="search",
                source="ai",
                status="success",
                progress=100,
                message="AI 检索历史已迁移。",
                request_json=json.dumps(request_data, ensure_ascii=False),
                result_json=json.dumps(search, ensure_ascii=False),
                dataset_id=plan.get("dataset_id"),
                created_by_id=run.user_id,
                created_at=run.created_at,
                updated_at=run.completed_at or run.updated_at,
            )
            db.session.add(task)
            db.session.flush()
            run.search_task_id = task.id
            summary = result.get("summary") or {}
            run.summary_status = "model" if summary.get("generated_by") == "model" else "fallback"
            changed = True
        if changed:
            db.session.commit()
