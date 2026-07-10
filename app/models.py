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
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    visibility = db.Column(db.String(20), default="private")   # private / shared
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    owner = db.relationship("User", backref="datasets")
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
    algorithm = db.Column(db.String(60), default="hnswlib_hnsw")
    preprocess_path = db.Column(db.String(500))
    params_json = db.Column(db.Text)
    index_size_bytes = db.Column(db.Integer)
    backend_version = db.Column(db.String(120))
    error_message = db.Column(db.Text)
    lifecycle = db.Column(db.String(20), default="active", nullable=False)
    selection_labels = db.Column(db.String(200))
    discarded_at = db.Column(db.DateTime)
    source_experiment_id = db.Column(db.Integer, db.ForeignKey("index_experiments.id", ondelete="SET NULL"))
    source_run_id = db.Column(db.Integer, db.ForeignKey("index_experiment_runs.id", ondelete="SET NULL"))
    metric = db.Column(db.String(20), default="l2")          # 距离度量：l2 或 cosine
    index_path = db.Column(db.String(500), nullable=False)   # 索引文件路径
    M = db.Column(db.Integer, default=16)                    # HNSW 参数 M
    ef_construction = db.Column(db.Integer, default=200)     # 构建时的 ef
    ef_search = db.Column(db.Integer, default=100)           # 查询时的 ef
    build_time_ms = db.Column(db.Float)                      # 构建耗时（毫秒）
    status = db.Column(db.String(20), default="building")    # building / ready / error
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    query_logs = db.relationship("QueryLog", backref="index", cascade="all, delete-orphan")
    source_experiment = db.relationship("IndexExperiment", foreign_keys=[source_experiment_id])
    source_run = db.relationship("IndexExperimentRun", foreign_keys=[source_run_id])


class IndexExperiment(db.Model):
    """Benchmark run comparing ANN algorithms for one dataset."""
    __tablename__ = "index_experiments"

    id = db.Column(db.Integer, primary_key=True)
    dataset_id = db.Column(db.Integer, db.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    metric = db.Column(db.String(20), default="l2")
    sample_size = db.Column(db.Integer, default=100)
    top_k = db.Column(db.Integer, default=10)
    seed = db.Column(db.Integer, default=42)
    repetitions = db.Column(db.Integer, default=3)
    warmup_count = db.Column(db.Integer, default=10)
    candidate_count = db.Column(db.Integer, default=0)
    config_json = db.Column(db.Text)
    status = db.Column(db.String(20), default="running")
    best_recall_run_id = db.Column(db.Integer)
    best_speed_run_id = db.Column(db.Integer)
    best_balanced_run_id = db.Column(db.Integer)
    exact_avg_query_time_ms = db.Column(db.Float)
    exact_p95_query_time_ms = db.Column(db.Float)
    selected_run_ids_json = db.Column(db.Text)
    finalized_at = db.Column(db.DateTime)
    reclaimed_bytes = db.Column(db.Integer, default=0)
    result_json = db.Column(db.Text)
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    dataset = db.relationship("Dataset", backref="index_experiments")
    runs = db.relationship("IndexExperimentRun", backref="experiment", cascade="all, delete-orphan")


class IndexExperimentRun(db.Model):
    """One candidate algorithm/config result in an index experiment."""
    __tablename__ = "index_experiment_runs"

    id = db.Column(db.Integer, primary_key=True)
    experiment_id = db.Column(db.Integer, db.ForeignKey("index_experiments.id", ondelete="CASCADE"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    algorithm = db.Column(db.String(60), nullable=False)
    params_json = db.Column(db.Text)
    status = db.Column(db.String(20), default="pending")
    skip_reason = db.Column(db.String(500))
    error_message = db.Column(db.Text)
    recall_at_k = db.Column(db.Float)
    avg_query_time_ms = db.Column(db.Float)
    p95_query_time_ms = db.Column(db.Float)
    avg_exact_time_ms = db.Column(db.Float)
    speedup = db.Column(db.Float)
    build_time_ms = db.Column(db.Float)
    index_size_bytes = db.Column(db.Integer)
    memory_bytes = db.Column(db.Integer)
    query_count = db.Column(db.Integer)
    quality = db.Column(db.String(40))
    recommendation = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class IndexEvaluation(db.Model):
    """Persistent index evaluation against an exact-search baseline."""
    __tablename__ = "index_evaluations"

    id = db.Column(db.Integer, primary_key=True)
    dataset_id = db.Column(db.Integer, db.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    index_id = db.Column(db.Integer, db.ForeignKey("ann_indexes.id", ondelete="CASCADE"), nullable=False)
    metric = db.Column(db.String(20), default="l2")
    algorithm = db.Column(db.String(60), default="hnswlib_hnsw")
    sample_size = db.Column(db.Integer, default=100)
    top_k = db.Column(db.Integer, default=10)
    seed = db.Column(db.Integer, default=42)
    recall_at_k = db.Column(db.Float)
    avg_query_time_ms = db.Column(db.Float)
    p95_query_time_ms = db.Column(db.Float)
    avg_exact_time_ms = db.Column(db.Float)
    speedup = db.Column(db.Float)
    index_size_bytes = db.Column(db.Integer)
    quality = db.Column(db.String(40))
    recommendation = db.Column(db.String(200))
    status = db.Column(db.String(20), default="running")
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    dataset = db.relationship("Dataset", backref="index_evaluations")
    ann_index = db.relationship("AnnIndex", backref="evaluations")


class JointIndex(db.Model):
    """Physical multi-dataset ANN index built in a shared corrected space."""
    __tablename__ = "joint_indexes"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    metric = db.Column(db.String(20), default="l2")
    index_path = db.Column(db.String(500))
    vector_path = db.Column(db.String(500))
    umap_path = db.Column(db.String(500))
    mapping_path = db.Column(db.String(500))
    M = db.Column(db.Integer, default=16)
    ef_construction = db.Column(db.Integer, default=200)
    ef_search = db.Column(db.Integer, default=100)
    n_pcs = db.Column(db.Integer, default=50)
    n_top_genes = db.Column(db.Integer, default=2000)
    min_common_genes = db.Column(db.Integer, default=500)
    common_gene_count = db.Column(db.Integer, default=0)
    n_cells = db.Column(db.Integer, default=0)
    build_time_ms = db.Column(db.Float)
    status = db.Column(db.String(20), default="building")
    error_message = db.Column(db.Text)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    owner = db.relationship("User", backref="joint_indexes")
    datasets = db.relationship("JointIndexDataset", backref="joint_index", cascade="all, delete-orphan")
    query_logs = db.relationship("JointQueryLog", backref="joint_index", cascade="all, delete-orphan")


class JointIndexDataset(db.Model):
    """Dataset inclusion/skipping record for a joint index build."""
    __tablename__ = "joint_index_datasets"

    id = db.Column(db.Integer, primary_key=True)
    joint_index_id = db.Column(db.Integer, db.ForeignKey("joint_indexes.id", ondelete="CASCADE"), nullable=False)
    dataset_id = db.Column(db.Integer, db.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    status = db.Column(db.String(20), default="included")
    n_cells = db.Column(db.Integer, default=0)
    skip_reason = db.Column(db.String(500))

    dataset = db.relationship("Dataset")

    __table_args__ = (
        db.Index("ix_joint_index_datasets_joint", "joint_index_id"),
        db.Index("ix_joint_index_datasets_dataset", "dataset_id"),
    )


class JointQueryLog(db.Model):
    """Query log for joint indexes."""
    __tablename__ = "joint_query_logs"

    id = db.Column(db.Integer, primary_key=True)
    joint_index_id = db.Column(db.Integer, db.ForeignKey("joint_indexes.id"), nullable=False)
    query_dataset_id = db.Column(db.Integer, db.ForeignKey("datasets.id"), nullable=False)
    query_cell_index = db.Column(db.Integer, nullable=False)
    top_k = db.Column(db.Integer, nullable=False)
    query_time_ms = db.Column(db.Float)
    result_count = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    query_dataset = db.relationship("Dataset")


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
