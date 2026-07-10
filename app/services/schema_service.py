"""轻量 SQLite 结构补齐，用于兼容课程项目中的既有本地数据库。"""
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
        "joint_indexes",
        "joint_index_datasets",
        "joint_query_logs",
        "index_experiments",
        "index_experiment_runs",
        "index_evaluations",
    ]:
        if not inspector.has_table(table_name):
            db.Model.metadata.tables[table_name].create(bind=engine, checkfirst=True)

    existing = {col["name"] for col in inspector.get_columns("datasets")}
    statements = []
    if "owner_id" not in existing:
        statements.append("ALTER TABLE datasets ADD COLUMN owner_id INTEGER")
    if "visibility" not in existing:
        statements.append("ALTER TABLE datasets ADD COLUMN visibility VARCHAR(20) DEFAULT 'private'")

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

    if not statements:
        return

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
