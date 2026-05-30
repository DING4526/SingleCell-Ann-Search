import os

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
    MAX_CONTENT_LENGTH = 3* 1024 * 1024 * 1024  # 上传大小限制 3GB
