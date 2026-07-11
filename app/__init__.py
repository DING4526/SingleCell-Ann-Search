import os
from flask import Flask, jsonify, request
from app.config import Config
from app.extensions import db, login_manager


def create_app(config_class=Config):
    """Flask 应用工厂，初始化应用并注册蓝图。"""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # 确保数据目录存在
    for d in [
        app.config["RAW_DIR"], app.config["CACHE_DIR"], app.config["INDEX_DIR"],
        app.config["KNOWLEDGE_DIR"],
    ]:
        os.makedirs(d, exist_ok=True)

    # 确保 SQLite 数据库目录存在
    instance_dir = os.path.dirname(app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", ""))
    os.makedirs(instance_dir, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    @login_manager.unauthorized_handler
    def unauthorized():
        if request.path.startswith("/api/"):
            return jsonify(ok=False, message="请先登录。"), 401
        from flask import redirect, url_for
        return redirect(url_for("auth.login", next=request.path))

    with app.app_context():
        from app.services.schema_service import ensure_sqlite_schema
        ensure_sqlite_schema()
        # Built-in knowledge is small and indexed locally. It is safe to seed
        # synchronously when upgrading an existing installation; fresh test
        # databases created after the app factory can seed explicitly.
        from sqlalchemy import inspect
        if inspect(db.engine).has_table("knowledge_documents"):
            from app.ai.knowledge import ensure_builtin_knowledge
            ensure_builtin_knowledge()
        if inspect(db.engine).has_table("ai_stream_events"):
            from app.ai.streaming import cleanup_stream_events
            cleanup_stream_events(app.config.get("AI_STREAM_EVENT_RETENTION_HOURS", 24))

    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    from app.routes.datasets import datasets_bp
    from app.routes.search import search_bp
    from app.routes.api import api_bp
    from app.routes.ai import ai_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(datasets_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(ai_bp)

    return app
