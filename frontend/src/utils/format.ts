export function formatDate(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function statusText(status: string) {
  return {
    uploaded: "已上传",
    processed: "已处理",
    indexed: "已建索引",
    error: "错误",
    ready: "就绪",
    building: "构建中",
    evaluating: "评估中",
    pending: "等待",
    running: "运行中",
    success: "完成",
    skipped: "已跳过",
    ready_for_selection: "待选优",
    finalized: "已完成选优",
    discarded: "已放弃",
    deleted: "已清理",
    cleanup_error: "清理失败",
    planned: "规划中",
    active: "可用于检索",
    candidate: "待选优",
    disabled: "已停用",
    extracting: "正在提取",
    indexing: "正在建立索引",
    degraded: "降级可用",
    rejected: "已拒绝",
    cancelled: "已取消",
    proposed: "待确认",
    queued: "排队中",
    not_started: "尚未开始",
    completed: "已完成",
    failed: "失败",
    approved: "已确认",
    expired: "已过期",
    included: "已纳入",
    excluded: "未纳入",
  }[status] || "状态未知";
}

export function statusColor(status: string) {
  if (["indexed", "ready", "success", "finalized", "active"].includes(status)) return "success";
  if (["processed", "running", "building", "evaluating"].includes(status)) return "processing";
  if (["uploaded", "pending"].includes(status)) return "default";
  if (["error", "cleanup_error"].includes(status)) return "error";
  if (["discarded", "deleted", "disabled", "cancelled"].includes(status)) return "default";
  return "default";
}

export function numberOrDash(value?: number | null) {
  return value === undefined || value === null ? "-" : value.toLocaleString();
}

export function formatDistance(value?: number | null) {
  if (value === undefined || value === null || !Number.isFinite(value)) return "-";
  return value.toLocaleString("zh-CN", { minimumFractionDigits: 3, maximumFractionDigits: 4 });
}

export function formatMilliseconds(value?: number | null) {
  if (value === undefined || value === null || !Number.isFinite(value)) return "-";
  const maximumFractionDigits = value < 1 ? 4 : value < 100 ? 3 : 1;
  return `${value.toLocaleString("zh-CN", { maximumFractionDigits })} ms`;
}

export function formatCellIndex(value?: number | null) {
  return value === undefined || value === null || !Number.isFinite(value) ? "-" : value.toLocaleString("zh-CN");
}

export function algorithmText(value?: string | null) {
  const normalized = (value || "").toLowerCase();
  return {
    hnswlib_hnsw: "HNSW",
    hnsw: "HNSW",
    rp_hnsw: "RP-HNSW",
    faiss_flat: "FAISS Flat",
    flat: "FAISS Flat",
    faiss_ivf_flat: "FAISS IVF-Flat",
    ivf_flat: "FAISS IVF-Flat",
    faiss_ivf_pq: "FAISS IVF-PQ",
    ivf_pq: "FAISS IVF-PQ",
  }[normalized] || "未知算法";
}

export function metricText(value?: string | null) {
  return {
    l2: "L2 欧氏距离",
    cosine: "余弦距离",
  }[(value || "").toLowerCase()] || "未知度量";
}

export function roleText(role?: string | null) {
  return {
    admin: "管理员",
    user: "普通用户",
  }[role || ""] || "未知角色";
}

export function taskTypeText(type?: string | null) {
  return {
    process: "处理数据集",
    build_index: "构建索引",
    index_experiment: "ANN 算法实验",
    search: "运行检索",
    search_plot: "生成检索图",
    multi_search: "跨数据集检索",
    index_evaluation: "真实索引评估",
    build_joint_index: "构建联合索引",
    joint_search: "联合索引检索",
    joint_search_plot: "生成联合图",
    artifact_cleanup: "清理资源文件",
  }[type || ""] || "后台任务";
}

export function visibilityText(visibility?: string | null) {
  return {
    public: "公开",
    private: "私有",
    shared: "共享",
  }[visibility || ""] || "未知范围";
}

export function qualityText(value?: string | null) {
  return {
    excellent: "优秀",
    acceptable: "可接受",
    low_recall: "召回偏低",
    not_recommended: "不推荐",
  }[value || ""] || value || "-";
}

export function qualityColor(value?: string | null) {
  return {
    excellent: "green",
    acceptable: "blue",
    low_recall: "orange",
    not_recommended: "red",
  }[value || ""] || "default";
}

export function recommendationText(value?: string | null) {
  return {
    best_recall: "最高召回",
    best_speed: "最快",
    best_balanced: "均衡推荐",
    acceptable_balanced: "可接受均衡",
    compact: "紧凑",
    fast_but_low_recall: "快但召回低",
    not_recommended: "不推荐",
  }[value || ""] || value || "-";
}

export function recommendationDescription(value?: string | null) {
  return {
    best_recall: "Recall@K 最高或并列最高。",
    best_speed: "在通过召回门槛的候选中平均耗时或 P95 最低。",
    best_balanced: "在高召回候选中取得更好的召回/延迟平衡。",
    compact: "索引体积明显低于同组中位数，同时通过召回门槛。",
    fast_but_low_recall: "速度最快，但 Recall@K 低于默认可用门槛。",
    not_recommended: "Recall@K 低于 0.80，不建议用于专业检索。",
  }[value || ""] || value || "";
}

export function recommendationColor(value?: string | null) {
  return {
    best_recall: "green",
    best_speed: "blue",
    best_balanced: "purple",
    compact: "cyan",
    fast_but_low_recall: "orange",
    not_recommended: "red",
  }[value || ""] || "default";
}
