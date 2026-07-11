from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from sqlalchemy import event
from sqlalchemy.engine import Engine


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    """Enforce SQLite foreign keys on every pooled connection.

    SQLite disables FK enforcement by default and enabling it once during
    application startup is not enough because SQLAlchemy may open additional
    connections later.  Registering at the engine level keeps production,
    tests, and one-off maintenance commands consistent.
    """
    del connection_record
    module_name = type(dbapi_connection).__module__.split(".", 1)[0]
    if module_name != "sqlite3":
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "请先登录后再访问该页面。"
