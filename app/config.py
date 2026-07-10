import os
from dotenv import load_dotenv

load_dotenv()

# 项目根目录
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'app.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 数据目录
    RAW_DIR = os.path.join(BASE_DIR, "data", "raw")          # 上传的 h5ad 文件
    CACHE_DIR = os.path.join(BASE_DIR, "data", "cache")      # 缓存的 npy 向量
    INDEX_DIR = os.path.join(BASE_DIR, "data", "indexes")    # HNSW 索引文件
    KNOWLEDGE_DIR = os.path.join(BASE_DIR, "data", "knowledge")
    MAX_CONTENT_LENGTH = 3* 1024 * 1024 * 1024  # 上传大小限制 3GB

    # AI integration. The encryption key must be a Fernet key and is deliberately
    # separate from Flask's session SECRET_KEY.
    AI_CREDENTIAL_ENCRYPTION_KEY = os.environ.get("AI_CREDENTIAL_ENCRYPTION_KEY", "")
    AI_ALLOW_PRIVATE_ENDPOINTS = os.environ.get("AI_ALLOW_PRIVATE_ENDPOINTS", "false").lower() in (
        "1", "true", "yes", "on"
    )
    AI_EXECUTOR_WORKERS = int(os.environ.get("AI_EXECUTOR_WORKERS", "2"))
    AI_KNOWLEDGE_MAX_FILE_MB = int(os.environ.get("AI_KNOWLEDGE_MAX_FILE_MB", "25"))
    AI_KNOWLEDGE_MAX_PDF_PAGES = int(os.environ.get("AI_KNOWLEDGE_MAX_PDF_PAGES", "500"))
    AI_STREAM_EVENT_RETENTION_HOURS = int(os.environ.get("AI_STREAM_EVENT_RETENTION_HOURS", "24"))
