import type { AiConversation, AiModelConfig, AiProviderCatalogItem, AiProviderConfig, AiRun, AiSettings, AiUsage, AnnAlgorithm, AuditEvent, Dataset, DatasetAccess, DatasetPermission, EvalMetrics, IndexCandidateConfig, IndexEvaluation, IndexExperiment, JointIndex, KnowledgeDocument, KnowledgeHit, ManagedUser, MultiSearchPayload, PlotlyPayload, SearchHistoryItem, SearchPlotPayload, SearchResult, SingleSearchPayload, TaskRecord, User } from "@/types";

type ApiResponse<T> = T & { ok: boolean; message?: string };
type ApiRequestInit = RequestInit & { timeoutMs?: number };

async function request<T>(url: string, options: ApiRequestInit = {}): Promise<T> {
  const { timeoutMs, ...fetchOptions } = options;
  const controller = timeoutMs ? new AbortController() : undefined;
  const timeoutId = timeoutMs ? window.setTimeout(() => controller?.abort(), timeoutMs) : undefined;

  try {
    const response = await fetch(url, {
      credentials: "same-origin",
      ...fetchOptions,
      signal: controller?.signal || fetchOptions.signal,
      headers: {
        ...(fetchOptions.body instanceof FormData ? {} : { "Content-Type": "application/x-www-form-urlencoded" }),
        ...(fetchOptions.headers || {}),
      },
    });

    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json") ? await response.json() : await response.text();
    if (!response.ok || (typeof payload === "object" && payload && payload.ok === false)) {
      const message = typeof payload === "object" && payload?.message ? payload.message : `请求失败 (${response.status})`;
      throw new Error(message);
    }
    return payload as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("请求超时，请稍后查看任务中心或重试");
    }
    throw error;
  } finally {
    if (timeoutId) window.clearTimeout(timeoutId);
  }
}

function toForm(data: Record<string, string | number | boolean | undefined | null>) {
  const form = new URLSearchParams();
  Object.entries(data).forEach(([key, value]) => {
    if (value !== undefined && value !== null) form.set(key, String(value));
  });
  return form;
}

function jsonRequest<T>(url: string, method: string, data: Record<string, unknown> = {}, timeoutMs?: number) {
  return request<T>(url, {
    method,
    body: JSON.stringify(data),
    headers: { "Content-Type": "application/json" },
    timeoutMs,
  });
}

function toSearchPlotForm(params: { dataset_id: number; query_cell_index: number; result_cell_indices: number[]; max_background_points?: number }) {
  const form = new FormData();
  form.set("dataset_id", String(params.dataset_id));
  form.set("query_cell_index", String(params.query_cell_index));
  form.set("max_background_points", String(params.max_background_points ?? 8_000));
  params.result_cell_indices.forEach((cellIndex) => form.append("result_cell_indices", String(cellIndex)));
  return form;
}

function toJointBuildForm(params: {
  name: string;
  dataset_ids: number[];
  metric: string;
  M: number;
  ef_construction: number;
  ef_search: number;
  n_pcs: number;
  n_top_genes: number;
  min_common_genes: number;
}) {
  const form = new FormData();
  form.set("name", params.name);
  form.set("metric", params.metric);
  form.set("M", String(params.M));
  form.set("ef_construction", String(params.ef_construction));
  form.set("ef_search", String(params.ef_search));
  form.set("n_pcs", String(params.n_pcs));
  form.set("n_top_genes", String(params.n_top_genes));
  form.set("min_common_genes", String(params.min_common_genes));
  params.dataset_ids.forEach((id) => form.append("dataset_ids", String(id)));
  return form;
}

function toJointPlotForm(params: { joint_index_id: number; query_global_label: number; result_global_labels: number[]; max_background_points?: number }) {
  const form = new FormData();
  form.set("joint_index_id", String(params.joint_index_id));
  form.set("query_global_label", String(params.query_global_label));
  form.set("max_background_points", String(params.max_background_points ?? 12_000));
  params.result_global_labels.forEach((label) => form.append("result_global_labels", String(label)));
  return form;
}

function toBuildIndexForm(params: { algorithm?: string; metric: string; M?: number; ef_construction?: number; ef_search?: number; projection_dim?: number; random_state?: number; nlist?: number; nprobe?: number; pq_m?: number; nbits?: number; params_json?: string; source_experiment_id?: number; source_run_id?: number }) {
  return toForm(params);
}

function toIndexExperimentForm(params: { dataset_id: number; metric: string; sample_size: number; top_k: number; seed?: number; repetitions?: number; warmup_count?: number; candidate_keys?: string[]; candidate_configs?: IndexCandidateConfig[] }) {
  const form = new FormData();
  form.set("dataset_id", String(params.dataset_id));
  form.set("metric", params.metric);
  form.set("sample_size", String(params.sample_size));
  form.set("top_k", String(params.top_k));
  form.set("seed", String(params.seed ?? 42));
  form.set("repetitions", String(params.repetitions ?? 3));
  form.set("warmup_count", String(params.warmup_count ?? 10));
  if (params.candidate_configs) form.set("candidate_configs", JSON.stringify(params.candidate_configs));
  (params.candidate_keys || []).forEach((key) => form.append("candidate_keys", key));
  return form;
}

function toSelectedRunsForm(selectedRunIds: number[]) {
  const form = new FormData();
  selectedRunIds.forEach((id) => form.append("selected_run_ids", String(id)));
  return form;
}

function toIndexEvaluationForm(params: { dataset_id: number; index_id: number; sample_size: number; top_k: number; seed?: number }) {
  return toForm({
    dataset_id: params.dataset_id,
    index_id: params.index_id,
    sample_size: params.sample_size,
    top_k: params.top_k,
    seed: params.seed ?? 42,
  });
}

export const api = {
  me: () => request<ApiResponse<{ authenticated: boolean; user: User | null }>>("/api/auth/me"),
  login: (username: string, password: string) =>
    request<ApiResponse<{ user: User }>>("/api/auth/login", { method: "POST", body: toForm({ username, password }) }),
  register: (username: string, password: string, confirm: string) =>
    request<ApiResponse<{ user: User }>>("/api/auth/register", { method: "POST", body: toForm({ username, password, confirm }) }),
  changePassword: (oldPassword: string, newPassword: string, confirm: string) =>
    request<ApiResponse<Record<string, never>>>("/api/auth/change-password", { method: "POST", body: toForm({ old_password: oldPassword, new_password: newPassword, confirm }) }),
  logout: () => request<ApiResponse<Record<string, never>>>("/api/auth/logout", { method: "POST", body: toForm({}) }),

  accessDatasets: () => request<ApiResponse<{ datasets: Dataset[] }>>("/api/access/datasets"),
  accessUsers: (query = "", role = "", status = "") => {
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (role) params.set("role", role);
    if (status) params.set("status", status);
    const suffix = params.toString() ? `?${params}` : "";
    return request<ApiResponse<{ users: ManagedUser[] }>>(`/api/access/users${suffix}`);
  },
  createUser: (params: { username: string; password: string; role: string }) =>
    request<ApiResponse<{ user: ManagedUser }>>("/api/access/users", { method: "POST", body: toForm(params) }),
  updateUser: (id: number, params: { role?: string; is_enabled?: boolean; ai_enabled?: boolean; ai_daily_limit_override?: number | "" }) =>
    request<ApiResponse<{ user: ManagedUser }>>(`/api/access/users/${id}`, { method: "PATCH", body: toForm(params) }),
  resetUserPassword: (id: number, newPassword: string) =>
    request<ApiResponse<Record<string, never>>>(`/api/access/users/${id}/reset-password`, { method: "POST", body: toForm({ new_password: newPassword }) }),
  datasetAccess: (id: number) => request<ApiResponse<{ access: DatasetAccess }>>(`/api/datasets/${id}/access`),
  updateDatasetVisibility: (id: number, visibility: "private" | "shared") =>
    request<ApiResponse<{ access: DatasetAccess }>>(`/api/datasets/${id}/access`, { method: "PATCH", body: toForm({ visibility }) }),
  saveDatasetPermission: (datasetId: number, userId: number, level: "viewer" | "editor") =>
    request<ApiResponse<{ permission: DatasetPermission }>>(`/api/datasets/${datasetId}/access/users/${userId}`, { method: "PUT", body: toForm({ level }) }),
  removeDatasetPermission: (datasetId: number, userId: number) =>
    request<ApiResponse<Record<string, never>>>(`/api/datasets/${datasetId}/access/users/${userId}`, { method: "DELETE" }),
  transferDatasetOwnership: (datasetId: number, newOwnerId: number) =>
    request<ApiResponse<{ dataset: Dataset }>>(`/api/datasets/${datasetId}/transfer-ownership`, { method: "POST", body: toForm({ new_owner_id: newOwnerId }) }),
  auditEvents: (params: { datasetId?: number; actorId?: number; event?: string; from?: string; to?: string; page?: number; pageSize?: number } = {}) => {
    const query = new URLSearchParams();
    if (params.datasetId) query.set("dataset_id", String(params.datasetId));
    if (params.actorId) query.set("actor_id", String(params.actorId));
    if (params.event) query.set("event", params.event);
    if (params.from) query.set("from", params.from);
    if (params.to) query.set("to", params.to);
    query.set("page", String(params.page ?? 1));
    query.set("page_size", String(params.pageSize ?? 30));
    return request<ApiResponse<{ events: AuditEvent[]; total: number; page: number; page_size: number }>>(`/api/access/audit?${query}`);
  },

  dashboardSummary: () => request<ApiResponse<Record<string, unknown>>>("/api/dashboard/summary"),
  datasets: () => request<ApiResponse<{ datasets: Dataset[] }>>("/api/datasets"),
  dataset: (id: number) =>
    request<ApiResponse<{ dataset: Dataset; stats: Record<string, { name: string; count: number }[]>; recent_tasks: TaskRecord[] }>>(`/api/datasets/${id}`),
  deleteDataset: (id: number) => request<ApiResponse<Record<string, never>>>(`/api/datasets/${id}`, { method: "DELETE" }),
  uploadDataset: (form: FormData) => request<ApiResponse<{ dataset_id: number; redirect_url: string }>>("/api/datasets/upload", { method: "POST", body: form }),
  processDataset: (id: number) => request<ApiResponse<{ task_id: number }>>(`/api/datasets/${id}/process`, { method: "POST", body: toForm({}) }),
  annAlgorithms: (datasetId?: number) => request<ApiResponse<{ algorithms: AnnAlgorithm[] }>>(`/api/ann/algorithms${datasetId ? `?dataset_id=${datasetId}` : ""}`),
  buildIndex: (id: number, params: { algorithm?: string; metric: string; M?: number; ef_construction?: number; ef_search?: number; projection_dim?: number; random_state?: number; nlist?: number; nprobe?: number; pq_m?: number; nbits?: number; params_json?: string; source_experiment_id?: number; source_run_id?: number }) =>
    request<ApiResponse<{ task_id: number }>>(`/api/datasets/${id}/build-index`, { method: "POST", body: toBuildIndexForm(params) }),
  jointIndexes: () => request<ApiResponse<{ joint_indexes: JointIndex[] }>>("/api/joint-indexes"),
  jointIndex: (id: number) => request<ApiResponse<{ joint_index: JointIndex }>>(`/api/joint-indexes/${id}`),
  buildJointIndexTask: (params: { name: string; dataset_ids: number[]; metric: string; M: number; ef_construction: number; ef_search: number; n_pcs: number; n_top_genes: number; min_common_genes: number }) =>
    request<ApiResponse<{ task_id: number }>>("/api/joint-indexes/build/task", { method: "POST", body: toJointBuildForm(params), timeoutMs: 15000 }),
  datasetStatus: (id: number) => request<ApiResponse<{ status: string; indexes: unknown[] }>>(`/api/datasets/${id}/status`),
  scatter: (id: number) => request<ApiResponse<{ scatter_plot: PlotlyPayload }>>(`/api/datasets/${id}/scatter`),
  cellTypes: (id: number) => request<ApiResponse<{ cell_types: string[] }>>(`/api/datasets/${id}/cell-types`),
  cellMeta: (datasetId: number, cellIndex: number) =>
    request<ApiResponse<{ cell: { cell_index: number; cell_name: string; cell_type: string; disease: string; age_group: string } }>>(
      `/api/datasets/${datasetId}/cell-meta/${cellIndex}`,
    ),
  tasks: (status = "all", limit = 20) => request<ApiResponse<{ tasks: TaskRecord[] }>>(`/api/tasks?status=${status}&limit=${limit}`, { timeoutMs: 5000 }),
  task: (id: number) => request<ApiResponse<TaskRecord>>(`/api/tasks/${id}`, { timeoutMs: 15000 }),
  activeTasks: () => request<ApiResponse<{ tasks: TaskRecord[] }>>("/api/tasks/active", { timeoutMs: 5000 }),
  search: (params: { dataset_id: number; index_id: number; query_cell_index: number; top_k: number; filter_cell_type?: string }) =>
    request<ApiResponse<SingleSearchPayload>>(
      "/api/search",
      { method: "POST", body: toForm(params) },
    ),
  searchTask: (params: { dataset_id: number; index_id: number; query_cell_index: number; top_k: number; filter_cell_type?: string; max_background_points?: number }) =>
    request<ApiResponse<{ task_id: number }>>("/api/search/task", { method: "POST", body: toForm(params), timeoutMs: 15000 }),
  searchPlotTask: (params: { dataset_id: number; query_cell_index: number; result_cell_indices: number[]; max_background_points?: number }) =>
    request<ApiResponse<{ task_id: number }>>("/api/search/plot/task", { method: "POST", body: toSearchPlotForm(params), timeoutMs: 15000 }),
  searchHistory: (filters: { mode?: string; source?: string; status?: string; limit?: number } = {}) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => { if (value !== undefined) params.set(key, String(value)); });
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return request<ApiResponse<{ history: SearchHistoryItem[] }>>(`/api/search/history${suffix}`);
  },
  searchHistoryDetail: (id: number) =>
    request<ApiResponse<{ history: SearchHistoryItem }>>(`/api/search/history/${id}`),
  hideSearchHistory: (id: number) =>
    request<ApiResponse<Record<string, never>>>(`/api/search/history/${id}`, { method: "DELETE" }),
  clearSearchHistory: (filters: { mode?: string; source?: string } = {}) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => { if (value && value !== "all") params.set(key, value); });
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return request<ApiResponse<{ hidden_count: number }>>(`/api/search/history${suffix}`, { method: "DELETE" });
  },
  multiSearch: (params: FormData) =>
    request<ApiResponse<MultiSearchPayload>>(
      "/api/search/multi",
      { method: "POST", body: params },
    ),
  multiSearchTask: (params: FormData) =>
    request<ApiResponse<{ task_id: number }>>("/api/search/multi/task", { method: "POST", body: params, timeoutMs: 15000 }),
  jointSearchTask: (params: { joint_index_id: number; query_dataset_id: number; query_cell_index: number; top_k: number }) =>
    request<ApiResponse<{ task_id: number }>>("/api/search/joint/task", { method: "POST", body: toForm(params), timeoutMs: 15000 }),
  jointSearchPlotTask: (params: { joint_index_id: number; query_global_label: number; result_global_labels: number[]; max_background_points?: number }) =>
    request<ApiResponse<{ task_id: number }>>("/api/search/joint/plot/task", { method: "POST", body: toJointPlotForm(params), timeoutMs: 15000 }),
  indexExperimentTask: (params: { dataset_id: number; metric: string; sample_size: number; top_k: number; seed?: number; repetitions?: number; warmup_count?: number; candidate_keys?: string[]; candidate_configs?: IndexCandidateConfig[] }) =>
    request<ApiResponse<{ task_id: number; experiment_id: number }>>("/api/index-experiments/task", { method: "POST", body: toIndexExperimentForm(params), timeoutMs: 15000 }),
  indexExperiments: (datasetId?: number) => request<ApiResponse<{ experiments: IndexExperiment[] }>>(`/api/index-experiments${datasetId ? `?dataset_id=${datasetId}` : ""}`),
  indexExperiment: (id: number) => request<ApiResponse<{ experiment: IndexExperiment }>>(`/api/index-experiments/${id}`),
  finalizeIndexExperiment: (id: number, selectedRunIds: number[]) =>
    request<ApiResponse<{ finalization: NonNullable<IndexExperiment["finalization"]> }>>(`/api/index-experiments/${id}/finalize`, { method: "POST", body: toSelectedRunsForm(selectedRunIds), timeoutMs: 30000 }),
  discardIndexExperiment: (id: number) =>
    request<ApiResponse<{ cleanup: Record<string, unknown> }>>(`/api/index-experiments/${id}/discard`, { method: "POST", body: toForm({}), timeoutMs: 30000 }),
  cleanupIndexExperiment: (id: number) =>
    request<ApiResponse<{ cleanup: Record<string, unknown> }>>(`/api/index-experiments/${id}/cleanup`, { method: "POST", body: toForm({}), timeoutMs: 30000 }),
  indexEvaluationTask: (params: { dataset_id: number; index_id: number; sample_size: number; top_k: number; seed?: number }) =>
    request<ApiResponse<{ task_id: number }>>("/api/index-evaluations/task", { method: "POST", body: toIndexEvaluationForm(params), timeoutMs: 15000 }),
  indexEvaluations: (datasetId?: number, indexId?: number) => {
    const params = new URLSearchParams();
    if (datasetId) params.set("dataset_id", String(datasetId));
    if (indexId) params.set("index_id", String(indexId));
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return request<ApiResponse<{ evaluations: IndexEvaluation[] }>>(`/api/index-evaluations${suffix}`);
  },
  indexEvaluation: (id: number) => request<ApiResponse<{ evaluation: IndexEvaluation }>>(`/api/index-evaluations/${id}`),
  evaluate: (params: { dataset_id: number; index_id: number; sample_size: number; eval_top_k: number }) =>
    request<ApiResponse<{ metrics: EvalMetrics; bar_plot: PlotlyPayload }>>("/api/evaluate", { method: "POST", body: toForm(params) }),

  aiCatalog: () => request<ApiResponse<{ providers: AiProviderCatalogItem[] }>>("/api/ai/catalog"),
  aiModels: () => request<ApiResponse<{ models: AiModelConfig[]; disabled: boolean }>>("/api/ai/models"),
  aiConversations: () => request<ApiResponse<{ conversations: AiConversation[] }>>("/api/ai/conversations"),
  createAiConversation: (title = "新建 AI 分析") =>
    jsonRequest<ApiResponse<{ conversation: AiConversation }>>("/api/ai/conversations", "POST", { title }),
  aiConversation: (id: number) => request<ApiResponse<{ conversation: AiConversation }>>(`/api/ai/conversations/${id}`),
  deleteAiConversation: (id: number) => request<ApiResponse<Record<string, never>>>(`/api/ai/conversations/${id}`, { method: "DELETE" }),
  sendAiMessage: (conversationId: number, content: string, modelConfigId: number, knowledgeScopes: string[] = ["platform", "dataset", "personal"]) =>
    jsonRequest<ApiResponse<{ run: AiRun }>>(`/api/ai/conversations/${conversationId}/messages`, "POST", { content, model_config_id: modelConfigId, knowledge_scopes: knowledgeScopes }, 15000),
  aiRun: (id: number) => request<ApiResponse<{ run: AiRun }>>(`/api/ai/runs/${id}`, { timeoutMs: 10000 }),
  updateAiRunPlan: (id: number, plan: Record<string, unknown>) =>
    jsonRequest<ApiResponse<{ run: AiRun; valid: boolean }>>(`/api/ai/runs/${id}/plan`, "PUT", plan),
  approveAiRun: (id: number) => jsonRequest<ApiResponse<{ run: AiRun }>>(`/api/ai/runs/${id}/approve`, "POST"),
  rejectAiRun: (id: number) => jsonRequest<ApiResponse<{ run: AiRun }>>(`/api/ai/runs/${id}/reject`, "POST"),
  cancelAiRun: (id: number) => jsonRequest<ApiResponse<{ run: AiRun }>>(`/api/ai/runs/${id}/cancel`, "POST"),
  aiCapabilities: () => request<ApiResponse<{ tools: Array<Record<string, unknown>> }>>("/api/ai/capabilities"),
  knowledgeDocuments: (scope?: string, datasetId?: number) => {
    const params = new URLSearchParams();
    if (scope) params.set("scope", scope);
    if (datasetId) params.set("dataset_id", String(datasetId));
    return request<ApiResponse<{ documents: KnowledgeDocument[] }>>(`/api/ai/knowledge/documents${params.toString() ? `?${params}` : ""}`);
  },
  uploadKnowledgeDocument: (params: { file: File; scope: string; title?: string; description?: string; dataset_id?: number }) => {
    const form = new FormData();
    form.set("file", params.file);
    form.set("scope", params.scope);
    if (params.title) form.set("title", params.title);
    if (params.description) form.set("description", params.description);
    if (params.dataset_id) form.set("dataset_id", String(params.dataset_id));
    return request<ApiResponse<{ document: KnowledgeDocument }>>("/api/ai/knowledge/documents", { method: "POST", body: form, timeoutMs: 30000 });
  },
  updateKnowledgeDocument: (id: number, params: Record<string, unknown>) => jsonRequest<ApiResponse<{ document: KnowledgeDocument }>>(`/api/ai/knowledge/documents/${id}`, "PATCH", params),
  deleteKnowledgeDocument: (id: number) => request<ApiResponse<Record<string, never>>>(`/api/ai/knowledge/documents/${id}`, { method: "DELETE" }),
  reindexKnowledgeDocument: (id: number) => jsonRequest<ApiResponse<{ document: KnowledgeDocument }>>(`/api/ai/knowledge/documents/${id}/reindex`, "POST"),
  previewKnowledgeSearch: (q: string, scopes: string[]) => request<ApiResponse<{ hits: KnowledgeHit[] }>>(`/api/ai/knowledge/search/preview?q=${encodeURIComponent(q)}&scopes=${encodeURIComponent(scopes.join(","))}`),
  syncBuiltinKnowledge: () => jsonRequest<ApiResponse<{ documents: KnowledgeDocument[] }>>("/api/ai/knowledge/builtin/sync", "POST"),

  aiAdminSettings: () => request<ApiResponse<{ settings: AiSettings; credential_store: { ready: boolean; message: string }; catalog: AiProviderCatalogItem[] }>>("/api/ai/admin/settings"),
  updateAiAdminSettings: (params: Partial<AiSettings>) =>
    jsonRequest<ApiResponse<{ settings: AiSettings; credential_store: { ready: boolean; message: string }; catalog: AiProviderCatalogItem[] }>>("/api/ai/admin/settings", "PATCH", params as Record<string, unknown>),
  aiAdminProviders: () => request<ApiResponse<{ providers: AiProviderConfig[] }>>("/api/ai/admin/providers"),
  createAiProvider: (params: Record<string, unknown>) => jsonRequest<ApiResponse<{ provider: AiProviderConfig }>>("/api/ai/admin/providers", "POST", params),
  updateAiProvider: (id: number, params: Record<string, unknown>) => jsonRequest<ApiResponse<{ provider: AiProviderConfig }>>(`/api/ai/admin/providers/${id}`, "PATCH", params),
  deleteAiProvider: (id: number) => request<ApiResponse<Record<string, never>>>(`/api/ai/admin/providers/${id}`, { method: "DELETE" }),
  aiAdminModels: () => request<ApiResponse<{ models: AiModelConfig[] }>>("/api/ai/admin/models"),
  createAiModel: (params: Record<string, unknown>) => jsonRequest<ApiResponse<{ model: AiModelConfig }>>("/api/ai/admin/models", "POST", params),
  updateAiModel: (id: number, params: Record<string, unknown>) => jsonRequest<ApiResponse<{ model: AiModelConfig }>>(`/api/ai/admin/models/${id}`, "PATCH", params),
  deleteAiModel: (id: number) => request<ApiResponse<Record<string, never>>>(`/api/ai/admin/models/${id}`, { method: "DELETE" }),
  testAiModel: (id: number) => jsonRequest<ApiResponse<{ model: AiModelConfig; latency_ms: number }>>(`/api/ai/admin/models/${id}/test`, "POST", {}, 190000),
  aiAdminUsage: () => request<ApiResponse<{ usage: AiUsage }>>("/api/ai/admin/usage"),
};
