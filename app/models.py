from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app.extensions import db, login_manager


class User(UserMixin, db.Model):
    """用户模型"""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default="user")       # 角色：user / admin
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        """设置密码（哈希存储）"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """校验密码"""
        return check_password_hash(self.password_hash, password)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class Dataset(db.Model):
    """数据集模型"""
    __tablename__ = "datasets"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default="")
    file_path = db.Column(db.String(500), nullable=False)    # h5ad 文件路径
    vector_path = db.Column(db.String(500))                  # npy 缓存路径
    n_cells = db.Column(db.Integer)                          # 细胞数
    n_genes = db.Column(db.Integer)                          # 基因数
    vector_dim = db.Column(db.Integer)                       # 向量维度
    status = db.Column(db.String(20), default="uploaded")    # uploaded / processed / indexed / error
    error_message = db.Column(db.Text)
    scatter_cache_path = db.Column(db.String(256))            # 散点图 Plotly JSON 缓存文件名
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    cells = db.relationship("Cell", backref="dataset", cascade="all, delete-orphan")
    indexes = db.relationship("AnnIndex", backref="dataset", cascade="all, delete-orphan")
    query_logs = db.relationship("QueryLog", backref="dataset", cascade="all, delete-orphan")


class Cell(db.Model):
    """细胞元信息模型"""
    __tablename__ = "cells"

    id = db.Column(db.Integer, primary_key=True)
    dataset_id = db.Column(db.Integer, db.ForeignKey("datasets.id"), nullable=False)
    cell_index = db.Column(db.Integer, nullable=False)       # AnnData 中的行号
    cell_name = db.Column(db.String(200))                    # 来自 adata.obs_names
    cell_type = db.Column(db.String(200))                    # 细胞类型
    disease = db.Column(db.String(200))                      # 疾病
    age_group = db.Column(db.String(200))                    # 年龄组
    metadata_json = db.Column(db.Text)                       # 其他 obs 字段的 JSON 存储

    __table_args__ = (
        db.Index("ix_cells_dataset_index", "dataset_id", "cell_index"),
        db.Index("ix_cells_dataset_type", "dataset_id", "cell_type"),
    )


class AnnIndex(db.Model):
    """ANN 索引模型"""
    __tablename__ = "ann_indexes"

    id = db.Column(db.Integer, primary_key=True)
    dataset_id = db.Column(db.Integer, db.ForeignKey("datasets.id"), nullable=False)
    metric = db.Column(db.String(20), default="l2")          # 距离度量：l2 或 cosine
    index_path = db.Column(db.String(500), nullable=False)   # 索引文件路径
    M = db.Column(db.Integer, default=16)                    # HNSW 参数 M
    ef_construction = db.Column(db.Integer, default=200)     # 构建时的 ef
    ef_search = db.Column(db.Integer, default=100)           # 查询时的 ef
    build_time_ms = db.Column(db.Float)                      # 构建耗时（毫秒）
    status = db.Column(db.String(20), default="ready")       # ready / error
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    query_logs = db.relationship("QueryLog", backref="index", cascade="all, delete-orphan")


class QueryLog(db.Model):
    """查询日志模型"""
    __tablename__ = "query_logs"

    id = db.Column(db.Integer, primary_key=True)
    dataset_id = db.Column(db.Integer, db.ForeignKey("datasets.id"), nullable=False)
    index_id = db.Column(db.Integer, db.ForeignKey("ann_indexes.id"), nullable=False)
    query_cell_index = db.Column(db.Integer, nullable=False) # 查询细胞索引
    top_k = db.Column(db.Integer, nullable=False)            # 返回结果数
    query_time_ms = db.Column(db.Float)                      # 查询耗时（毫秒）
    result_count = db.Column(db.Integer)                     # 实际返回结果数
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Task(db.Model):
    """后台任务模型：跟踪异步任务状态与进度"""
    __tablename__ = "tasks"

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(30), nullable=False)           # upload/process/build_index/search/evaluate
    status = db.Column(db.String(20), default="pending")      # pending/running/success/error
    progress = db.Column(db.Integer, default=0)               # 0-100
    message = db.Column(db.String(500), default="")           # 当前阶段描述
    result_json = db.Column(db.Text)                          # JSON 格式的任务结果
    error_message = db.Column(db.Text)                        # 错误信息
    dataset_id = db.Column(db.Integer, db.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
