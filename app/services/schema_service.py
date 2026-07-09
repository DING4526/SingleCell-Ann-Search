"""轻量 SQLite 结构补齐，用于兼容课程项目中的既有本地数据库。"""
from sqlalchemy import inspect, text
from app.extensions import db


def ensure_sqlite_schema():
    engine = db.engine
    if not engine.url.drivername.startswith("sqlite"):
        return

    inspector = inspect(engine)
    if not inspector.has_table("datasets"):
        return

    existing = {col["name"] for col in inspector.get_columns("datasets")}
    statements = []
    if "owner_id" not in existing:
        statements.append("ALTER TABLE datasets ADD COLUMN owner_id INTEGER")
    if "visibility" not in existing:
        statements.append("ALTER TABLE datasets ADD COLUMN visibility VARCHAR(20) DEFAULT 'private'")

    if not statements:
        return

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
