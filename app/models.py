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
    is_enabled = db.Column(db.Boolean, default=True, nullable=False)
    ai_enabled = db.Column(db.Boolean, default=True, nullable=False)
    ai_daily_limit_override = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def is_active(self):
        """Flask-Login uses this flag to reject disabled accounts."""
        return bool(self.is_enabled)

    def set_password(self, password):
        """设置密码（哈希存储）"""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        """校验密码"""
        return check_password_hash(self.password_hash, password)


@login_manager.user_loader
def load_user(user_id):
    user = db.session.get(User, int(user_id))
    return user if user and user.is_enabled else None


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
    permissions = db.relationship("DatasetPermission", backref="dataset", cascade="all, delete-orphan")


class DatasetPermission(db.Model):
    """Explicit per-user Viewer/Editor grant for a dataset."""
    __tablename__ = "dataset_permissions"

    id = db.Column(db.Integer, primary_key=True)
    dataset_id = db.Column(db.Integer, db.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    level = db.Column(db.String(20), nullable=False)  # viewer / editor
    granted_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = db.relationship("User", foreign_keys=[user_id], backref="dataset_permissions")
    granted_by = db.relationship("User", foreign_keys=[granted_by_id])

    __table_args__ = (
        db.UniqueConstraint("dataset_id", "user_id", name="uq_dataset_permissions_dataset_user"),
        db.Index("ix_dataset_permissions_user", "user_id"),
    )


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
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
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
    created_by = db.relationship("User", foreign_keys=[created_by_id])
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
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
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
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
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
    request_json = db.Column(db.Text)                         # 可复现检索请求
    source = db.Column(db.String(30), default="query_lab", nullable=False)
    history_hidden = db.Column(db.Boolean, default=False, nullable=False)
    error_message = db.Column(db.Text)                        # 错误信息
    dataset_id = db.Column(db.Integer, db.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    created_by = db.relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        db.Index("ix_tasks_owner_history", "created_by_id", "history_hidden", "updated_at"),
    )


class AuditLog(db.Model):
    """Security and write-operation audit event."""
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    event = db.Column(db.String(80), nullable=False)
    resource_type = db.Column(db.String(40))
    resource_id = db.Column(db.Integer)
    dataset_id = db.Column(db.Integer, db.ForeignKey("datasets.id", ondelete="SET NULL"))
    target_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    details_json = db.Column(db.Text)
    ip_address = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    actor = db.relationship("User", foreign_keys=[actor_id])
    target_user = db.relationship("User", foreign_keys=[target_user_id])

    __table_args__ = (
        db.Index("ix_audit_logs_dataset_created", "dataset_id", "created_at"),
        db.Index("ix_audit_logs_actor_created", "actor_id", "created_at"),
    )


class AiSystemSettings(db.Model):
    """Singleton settings row for the platform AI feature."""
    __tablename__ = "ai_system_settings"

    id = db.Column(db.Integer, primary_key=True, default=1)
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    daily_request_limit = db.Column(db.Integer, default=50, nullable=False)
    max_concurrent_runs = db.Column(db.Integer, default=1, nullable=False)
    max_prompt_chars = db.Column(db.Integer, default=4000, nullable=False)
    rag_enabled = db.Column(db.Boolean, default=True, nullable=False)
    default_knowledge_top_k = db.Column(db.Integer, default=8, nullable=False)
    max_knowledge_file_mb = db.Column(db.Integer, default=25, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class AiProviderConfig(db.Model):
    """Administrator-managed provider credential shared by enabled users."""
    __tablename__ = "ai_provider_configs"

    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(30), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    base_url = db.Column(db.String(500), nullable=False)
    api_key_ciphertext = db.Column(db.Text, nullable=False)
    api_key_hint = db.Column(db.String(32), nullable=False)
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    timeout_seconds = db.Column(db.Integer, default=180, nullable=False)
    last_test_status = db.Column(db.String(20), default="untested", nullable=False)
    last_test_message = db.Column(db.String(500))
    last_tested_at = db.Column(db.DateTime)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    created_by = db.relationship("User", foreign_keys=[created_by_id])

    model_configs = db.relationship(
        "AiModelConfig", backref="provider_config", cascade="all, delete-orphan"
    )


class AiModelConfig(db.Model):
    """One selectable model exposed through an administrator provider config."""
    __tablename__ = "ai_model_configs"

    id = db.Column(db.Integer, primary_key=True)
    provider_config_id = db.Column(
        db.Integer, db.ForeignKey("ai_provider_configs.id", ondelete="CASCADE"), nullable=False
    )
    model_id = db.Column(db.String(200), nullable=False)
    display_name = db.Column(db.String(200), nullable=False)
    capability = db.Column(db.String(20), default="chat", nullable=False)  # chat / embedding
    embedding_dimensions = db.Column(db.Integer)
    enabled = db.Column(db.Boolean, default=False, nullable=False)
    is_default = db.Column(db.Boolean, default=False, nullable=False)
    last_test_status = db.Column(db.String(20), default="untested", nullable=False)
    last_test_message = db.Column(db.String(500))
    last_tested_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("provider_config_id", "model_id", name="uq_ai_provider_model"),
    )


class AiConversation(db.Model):
    """Private, user-owned AI conversation."""
    __tablename__ = "ai_conversations"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = db.Column(db.String(200), default="新建 AI 分析", nullable=False)
    kind = db.Column(db.String(20), default="analysis", nullable=False)  # analysis / assistant
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = db.relationship("User", foreign_keys=[user_id])
    messages = db.relationship("AiMessage", backref="conversation", cascade="all, delete-orphan")
    runs = db.relationship("AiRun", backref="conversation", cascade="all, delete-orphan")


class AiMessage(db.Model):
    """A persisted user or assistant message; visible only to the owner."""
    __tablename__ = "ai_messages"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(
        db.Integer, db.ForeignKey("ai_conversations.id", ondelete="CASCADE"), nullable=False
    )
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    structured_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class AiRun(db.Model):
    """Stateful planning/execution record for an AI analysis request."""
    __tablename__ = "ai_runs"

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(
        db.Integer, db.ForeignKey("ai_conversations.id", ondelete="CASCADE"), nullable=False
    )
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    model_config_id = db.Column(
        db.Integer, db.ForeignKey("ai_model_configs.id", ondelete="RESTRICT"), nullable=False
    )
    input_message_id = db.Column(db.Integer, db.ForeignKey("ai_messages.id", ondelete="SET NULL"))
    output_message_id = db.Column(db.Integer, db.ForeignKey("ai_messages.id", ondelete="SET NULL"))
    context_run_id = db.Column(db.Integer, db.ForeignKey("ai_runs.id", ondelete="SET NULL"))
    search_task_id = db.Column(db.Integer, db.ForeignKey("tasks.id", ondelete="SET NULL"))
    intent = db.Column(db.String(40), default="single_cell_search", nullable=False)
    status = db.Column(db.String(30), default="queued", nullable=False)
    progress = db.Column(db.Integer, default=0, nullable=False)
    summary_status = db.Column(db.String(30), default="not_started", nullable=False)
    summary_message = db.Column(db.String(500))
    response_language = db.Column(db.String(20), default="zh-CN", nullable=False)
    surface = db.Column(db.String(20), default="analysis", nullable=False)
    page_context_json = db.Column(db.Text)
    prompt_revision = db.Column(db.String(60))
    cancel_requested = db.Column(db.Boolean, default=False, nullable=False)
    phase_json = db.Column(db.Text)
    plan_json = db.Column(db.Text)
    result_json = db.Column(db.Text)
    error_code = db.Column(db.String(80))
    error_message = db.Column(db.String(500))
    provider_request_count = db.Column(db.Integer, default=0, nullable=False)
    input_tokens = db.Column(db.Integer, default=0, nullable=False)
    output_tokens = db.Column(db.Integer, default=0, nullable=False)
    latency_ms = db.Column(db.Float, default=0.0, nullable=False)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = db.relationship("User", foreign_keys=[user_id])
    model_config = db.relationship("AiModelConfig", foreign_keys=[model_config_id], backref="runs")
    input_message = db.relationship("AiMessage", foreign_keys=[input_message_id])
    output_message = db.relationship("AiMessage", foreign_keys=[output_message_id])
    context_run = db.relationship("AiRun", remote_side=[id], foreign_keys=[context_run_id])
    search_task = db.relationship("Task", foreign_keys=[search_task_id])
    tool_calls = db.relationship("AiToolCall", backref="run", cascade="all, delete-orphan")

    __table_args__ = (
        db.Index("ix_ai_runs_user_created", "user_id", "created_at"),
        db.Index("ix_ai_runs_status", "status"),
    )


class AiToolCall(db.Model):
    """Auditable, explicitly approved platform tool call proposed by an AI run."""
    __tablename__ = "ai_tool_calls"

    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey("ai_runs.id", ondelete="CASCADE"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(30), default="proposed", nullable=False)
    args_json = db.Column(db.Text)
    result_json = db.Column(db.Text)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id", ondelete="SET NULL"))
    order_index = db.Column(db.Integer, default=0, nullable=False)
    approved_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    risk_level = db.Column(db.String(20), default="read", nullable=False)
    idempotency_key = db.Column(db.String(64))
    expires_at = db.Column(db.DateTime)
    precondition_json = db.Column(db.Text)
    approved_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    approved_by = db.relationship("User", foreign_keys=[approved_by_id])
    task = db.relationship("Task", foreign_keys=[task_id])

    __table_args__ = (
        db.Index("ix_ai_tool_calls_idempotency", "idempotency_key", unique=True),
    )


class KnowledgeDocument(db.Model):
    """An uploaded or built-in document available to the grounded AI layer."""
    __tablename__ = "knowledge_documents"

    id = db.Column(db.Integer, primary_key=True)
    scope = db.Column(db.String(20), nullable=False)  # platform / dataset / personal
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"))
    dataset_id = db.Column(db.Integer, db.ForeignKey("datasets.id", ondelete="CASCADE"))
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, default="")
    original_filename = db.Column(db.String(300))
    stored_path = db.Column(db.String(500))
    mime_type = db.Column(db.String(120))
    size_bytes = db.Column(db.Integer, default=0, nullable=False)
    checksum = db.Column(db.String(64), nullable=False)
    source_type = db.Column(db.String(30), default="upload", nullable=False)  # upload / builtin
    source_key = db.Column(db.String(200))
    version = db.Column(db.String(40), default="1", nullable=False)
    status = db.Column(db.String(30), default="pending", nullable=False)
    semantic_status = db.Column(db.String(30), default="not_configured", nullable=False)
    page_count = db.Column(db.Integer)
    chunk_count = db.Column(db.Integer, default=0, nullable=False)
    error_message = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    owner = db.relationship("User", foreign_keys=[owner_id])
    dataset = db.relationship("Dataset", foreign_keys=[dataset_id])
    chunks = db.relationship("KnowledgeChunk", backref="document", cascade="all, delete-orphan")

    __table_args__ = (
        db.Index("ix_knowledge_documents_scope_status", "scope", "status"),
        db.Index("ix_knowledge_documents_owner", "owner_id", "created_at"),
        db.Index("ix_knowledge_documents_dataset", "dataset_id", "created_at"),
        db.UniqueConstraint("source_type", "source_key", name="uq_knowledge_builtin_source"),
    )


class KnowledgeChunk(db.Model):
    """A paragraph-aware RAG chunk with an optional provider embedding."""
    __tablename__ = "knowledge_chunks"

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(
        db.Integer, db.ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index = db.Column(db.Integer, nullable=False)
    heading = db.Column(db.String(500))
    page_number = db.Column(db.Integer)
    content = db.Column(db.Text, nullable=False)
    content_hash = db.Column(db.String(64), nullable=False)
    embedding_blob = db.Column(db.LargeBinary)
    embedding_dimensions = db.Column(db.Integer)
    embedding_model_config_id = db.Column(
        db.Integer, db.ForeignKey("ai_model_configs.id", ondelete="SET NULL")
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    embedding_model = db.relationship("AiModelConfig", foreign_keys=[embedding_model_config_id])

    __table_args__ = (
        db.UniqueConstraint("document_id", "chunk_index", name="uq_knowledge_chunk_position"),
        db.Index("ix_knowledge_chunks_document", "document_id", "chunk_index"),
    )


class AiCitation(db.Model):
    """Stable citation snapshot attached to one private assistant message."""
    __tablename__ = "ai_citations"

    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey("ai_messages.id", ondelete="CASCADE"), nullable=False)
    chunk_id = db.Column(db.Integer, db.ForeignKey("knowledge_chunks.id", ondelete="SET NULL"))
    citation_key = db.Column(db.String(80), nullable=False)
    source_title = db.Column(db.String(300), nullable=False)
    heading = db.Column(db.String(500))
    page_number = db.Column(db.Integer)
    excerpt = db.Column(db.String(300), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    message = db.relationship("AiMessage", foreign_keys=[message_id])
    chunk = db.relationship("KnowledgeChunk", foreign_keys=[chunk_id])

    __table_args__ = (db.Index("ix_ai_citations_message", "message_id"),)


class AiStreamEvent(db.Model):
    """Replayable private SSE event for an AI run."""
    __tablename__ = "ai_stream_events"

    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey("ai_runs.id", ondelete="CASCADE"), nullable=False)
    sequence = db.Column(db.Integer, nullable=False)
    event_type = db.Column(db.String(50), nullable=False)
    payload_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    run = db.relationship("AiRun", foreign_keys=[run_id])

    __table_args__ = (
        db.UniqueConstraint("run_id", "sequence", name="uq_ai_stream_run_sequence"),
        db.Index("ix_ai_stream_events_run", "run_id", "sequence"),
    )


class AiProviderCall(db.Model):
    """Prompt-free accounting for chat and embedding provider requests."""
    __tablename__ = "ai_provider_calls"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    run_id = db.Column(db.Integer, db.ForeignKey("ai_runs.id", ondelete="SET NULL"))
    document_id = db.Column(db.Integer, db.ForeignKey("knowledge_documents.id", ondelete="SET NULL"))
    model_config_id = db.Column(db.Integer, db.ForeignKey("ai_model_configs.id", ondelete="SET NULL"))
    operation = db.Column(db.String(40), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    request_count = db.Column(db.Integer, default=1, nullable=False)
    input_tokens = db.Column(db.Integer, default=0, nullable=False)
    output_tokens = db.Column(db.Integer, default=0, nullable=False)
    latency_ms = db.Column(db.Float, default=0.0, nullable=False)
    error_code = db.Column(db.String(80))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.Index("ix_ai_provider_calls_model_created", "model_config_id", "created_at"),
        db.Index("ix_ai_provider_calls_user_created", "user_id", "created_at"),
    )
