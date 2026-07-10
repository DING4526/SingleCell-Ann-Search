export type User = {
  id: number;
  username: string;
  role: "user" | "admin" | string;
  is_admin: boolean;
  is_enabled: boolean;
  ai_enabled: boolean;
  ai_daily_limit_override: number | null;
};

export type EffectiveRole = "admin" | "owner" | "editor" | "viewer";
export type PermissionSource = "admin" | "owner" | "explicit" | "shared";

export type ManagedUser = User & {
  created_at?: string | null;
  owned_dataset_count?: number;
};

export type DatasetPermission = {
  id: number;
  dataset_id: number;
  user_id: number;
  username: string | null;
  user_enabled: boolean;
  level: "viewer" | "editor";
  granted_by_id: number | null;
  granted_by_name: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type DatasetAccess = {
  dataset_id: number;
  visibility: "private" | "shared";
  owner: User | null;
  permissions: DatasetPermission[];
};

export type AuditEvent = {
  id: number;
  event: string;
  actor_id: number | null;
  actor_name: string | null;
  resource_type: string | null;
  resource_id: number | null;
  dataset_id: number | null;
  target_user_id: number | null;
  target_user_name: string | null;
  details: Record<string, unknown>;
  ip_address: string | null;
  created_at: string | null;
};

export type AnnIndex = {
  id: number;
  dataset_id: number;
  algorithm: string;
  params?: Record<string, unknown>;
  metric: "l2" | "cosine" | string;
  M: number;
  ef_construction: number;
  ef_search: number;
  build_time_ms: number | null;
  index_size_bytes?: number | null;
  backend_version?: string | null;
  source_experiment_id?: number | null;
  source_run_id?: number | null;
  source_run?: IndexSourceRun | null;
  lifecycle: "candidate" | "active" | "discarded" | string;
  selection_labels: string[];
  discarded_at?: string | null;
  status: "building" | "ready" | "error" | "deleted" | "cleanup_error" | string;
  error_message?: string | null;
  created_at: string | null;
};

export type AnnAlgorithm = {
  key: string;
  label: string;
  family: string;
  available: boolean;
  disabled_reason: string | null;
  supports_metrics: string[];
  default_params: Record<string, number | string>;
  backend_version: string | null;
};

export type IndexExperimentRun = {
  id: number;
  name: string;
  algorithm: string;
  params: Record<string, unknown>;
  status: "pending" | "building" | "evaluating" | "success" | "skipped" | "error" | string;
  skip_reason: string | null;
  error_message: string | null;
  recall_at_k: number | null;
  avg_query_time_ms: number | null;
  p95_query_time_ms: number | null;
  avg_exact_time_ms: number | null;
  speedup: number | null;
  build_time_ms: number | null;
  index_size_bytes: number | null;
  memory_bytes: number | null;
  query_count: number | null;
  quality: string | null;
  recommendation: string | null;
  index: {
    id: number;
    algorithm: string;
    metric: string;
    lifecycle: string;
    selection_labels: string[];
    status: string;
    index_size_bytes: number | null;
    build_time_ms: number | null;
    error_message: string | null;
  } | null;
};

export type IndexCandidateConfig = {
  key: string;
  name: string;
  algorithm: string;
  params: Record<string, number | string>;
};

export type IndexSourceRun = Pick<
  IndexExperimentRun,
  | "id"
  | "name"
  | "algorithm"
  | "params"
  | "status"
  | "recall_at_k"
  | "avg_query_time_ms"
  | "p95_query_time_ms"
  | "avg_exact_time_ms"
  | "speedup"
  | "build_time_ms"
  | "index_size_bytes"
  | "quality"
  | "recommendation"
> & {
  experiment_id: number;
};

export type IndexExperiment = {
  id: number;
  dataset_id: number;
  dataset_name: string | null;
  created_by_id?: number | null;
  created_by_name?: string | null;
  metric: "l2" | "cosine" | string;
  sample_size: number;
  top_k: number;
  seed: number;
  repetitions: number;
  warmup_count: number;
  candidate_count: number;
  config: { workflow_version?: number; exact_backend?: string; candidates?: IndexCandidateConfig[] };
  workflow_version: number;
  status: string;
  best_recall_run_id: number | null;
  best_speed_run_id: number | null;
  best_balanced_run_id: number | null;
  recommended_run_ids: number[];
  exact_baseline: {
    algorithm: string;
    avg_query_time_ms: number | null;
    p95_query_time_ms: number | null;
  };
  selected_run_ids: number[];
  finalized_at: string | null;
  reclaimed_bytes: number;
  finalizable: boolean;
  finalization?: {
    active_indexes: Array<Record<string, unknown>>;
    selected_run_ids: number[];
    discarded_index_ids: number[];
    reclaimed_bytes: number;
    cleanup_errors: Array<Record<string, unknown>>;
  };
  error_message: string | null;
  created_at: string | null;
  runs?: IndexExperimentRun[];
};

export type IndexEvaluation = {
  id: number;
  dataset_id: number;
  dataset_name: string | null;
  index_id: number;
  index_label: string | null;
  algorithm: string;
  metric: "l2" | "cosine" | string;
  sample_size: number;
  top_k: number;
  seed: number;
  recall_at_k: number | null;
  avg_query_time_ms: number | null;
  p95_query_time_ms: number | null;
  avg_exact_time_ms: number | null;
  speedup: number | null;
  index_size_bytes: number | null;
  quality: string | null;
  quality_gate: string | null;
  recommendation: string | null;
  status: string;
  error_message: string | null;
  created_at: string | null;
};

export type JointIndexDataset = {
  dataset_id: number;
  dataset_name: string | null;
  status: "included" | "skipped" | string;
  n_cells: number;
  skip_reason: string | null;
};

export type JointIndex = {
  id: number;
  name: string;
  metric: "l2" | "cosine" | string;
  M: number;
  ef_construction: number;
  ef_search: number;
  n_pcs: number;
  n_top_genes: number;
  min_common_genes: number;
  common_gene_count: number;
  n_cells: number;
  build_time_ms: number | null;
  status: "building" | "ready" | "error" | string;
  error_message: string | null;
  owner_id: number | null;
  created_at: string | null;
  datasets: JointIndexDataset[];
};

export type Dataset = {
  id: number;
  name: string;
  description: string;
  n_cells: number | null;
  n_genes: number | null;
  vector_dim: number | null;
  status: "uploaded" | "processed" | "indexed" | "error" | string;
  error_message: string | null;
  owner_id: number | null;
  owner_name: string | null;
  visibility: "private" | "shared" | string;
  created_at: string | null;
  effective_role: EffectiveRole | null;
  permission_source: PermissionSource | null;
  can_edit: boolean;
  can_manage: boolean;
  indexes: AnnIndex[];
  ready_index_count: number;
};

export type TaskRecord = {
  id: number;
  type: string;
  status: "pending" | "running" | "success" | "error" | string;
  progress: number;
  message: string;
  error: string | null;
  result: unknown;
  has_result?: boolean;
  dataset_id: number | null;
  dataset_name: string | null;
  created_by_id: number | null;
  created_by_name: string | null;
  updated_at: string | null;
};

export type SearchResult = {
  rank: number;
  global_label?: number;
  dataset_id?: number;
  dataset_name?: string;
  index_id?: number;
  cell_id: number | null;
  cell_index: number;
  cell_name: string;
  distance: number;
  cell_type: string;
  disease: string;
  age_group: string;
};

export type PlotlyPayload = {
  data: unknown[];
  layout: Record<string, unknown>;
  metadata?: Record<string, unknown>;
};

export type EvalMetrics = {
  avg_recall_at_k: number;
  avg_ann_time_ms: number;
  p95_query_time_ms?: number;
  avg_exact_time_ms: number;
  speedup: number;
  sample_size: number;
  top_k: number;
  seed?: number;
  quality?: string;
  quality_gate?: string;
};

export type SingleSearchPayload = {
  result_data: {
    results: SearchResult[];
    query_time_ms: number;
    query_cell_index: number;
    top_k: number;
  };
  scatter_plot?: PlotlyPayload;
  interpretation: Record<string, unknown>;
};

export type SearchPlotPayload = {
  scatter_plot: PlotlyPayload;
};

export type MultiSearchPayload = {
  result_data: {
    results: SearchResult[];
    query_time_ms: number;
    query_cell_index: number;
    top_k: number;
    searched_dataset_count: number;
    skipped: unknown[];
    metric: string;
  };
};

export type JointSearchPayload = {
  result_data: {
    results: SearchResult[];
    query_time_ms: number;
    query_dataset_id: number;
    query_cell_index: number;
    query_global_label: number;
    joint_index_id: number;
    top_k: number;
    searched_dataset_count: number;
    metric: string;
  };
};

export type AiProviderCatalogItem = {
  key: string;
  label: string;
  default_base_url: string;
  base_url_options: Array<{ label: string; value: string }>;
  suggested_models: string[];
  suggested_embedding_models: string[];
};

export type AiSettings = {
  enabled: boolean;
  daily_request_limit: number;
  max_concurrent_runs: number;
  max_prompt_chars: number;
  rag_enabled: boolean;
  default_knowledge_top_k: number;
  max_knowledge_file_mb: number;
  updated_at: string | null;
};

export type AiProviderConfig = {
  id: number;
  provider: string;
  name: string;
  base_url: string;
  api_key_hint: string;
  enabled: boolean;
  timeout_seconds: number;
  last_test_status: string;
  last_test_message: string | null;
  last_tested_at: string | null;
  created_at: string | null;
};

export type AiModelConfig = {
  id: number;
  provider_config_id?: number;
  provider: string;
  provider_name: string;
  model_id: string;
  display_name: string;
  capability: "chat" | "embedding" | string;
  embedding_dimensions?: number | null;
  enabled: boolean;
  is_default: boolean;
  last_test_status: string;
  last_test_message?: string | null;
  last_tested_at?: string | null;
  created_at?: string | null;
};

export type AiSearchPlan = {
  intent: "single_cell_search";
  dataset_reference: string | number | null;
  dataset_id?: number | null;
  dataset_name?: string | null;
  dataset_options?: Array<{ id: number; name: string; n_cells: number | null }>;
  query_cell_index: number | null;
  top_k: number;
  filter_cell_type: string | null;
  cell_type_options?: string[];
  index_reference: string | number | null;
  index_id?: number | null;
  index_label?: string | null;
  index_options?: Array<{ id: number; algorithm: string; metric: string; labels: string[] }>;
  index_policy: "explicit" | "best_balanced" | "latest_ready";
  analysis_dimensions: string[];
  validation_errors?: string[];
};

export type AiAnalysisStep = {
  tool: "get_dataset_profile" | "retrieve_knowledge" | "run_single_cell_search" | "run_fanout_search" | "run_joint_search" | "compare_result_sets" | "build_evidence_report" | string;
  selection_mode?: "auto" | "explicit";
  dataset_reference?: string | number | null;
  dataset_id?: number | null;
  dataset_name?: string | null;
  dataset_options?: Array<{ id: number; name: string; n_cells: number | null }>;
  index_reference?: string | number | null;
  index_id?: number | null;
  joint_index_reference?: string | number | null;
  joint_index_id?: number | null;
  joint_index_name?: string | null;
  query_cell_index?: number | null;
  top_k?: number;
  filter_cell_type?: string | null;
  target_dataset_ids?: number[];
  target_dataset_references?: Array<string | number>;
  validation_errors?: string[];
};

export type AiAnalysisPlan = {
  intent: "analysis_request";
  goal: string;
  response_language: string;
  knowledge_scopes: Array<"platform" | "dataset" | "personal">;
  steps: AiAnalysisStep[];
  expected_outputs: string[];
  validation_errors?: string[];
  dataset_id?: number | null;
  dataset_reference?: string | number | null;
  dataset_name?: string | null;
  index_id?: number | null;
  index_reference?: string | number | null;
  joint_index_id?: number | null;
  query_cell_index?: number | null;
  top_k?: number;
  filter_cell_type?: string | null;
  cell_type_options?: string[];
  target_dataset_ids?: number[];
};

export type AiAnalysisSummary = {
  headline: string;
  summary: string;
  findings: Array<{ statement: string; evidence_keys: string[] }>;
  caveats: string[];
  next_actions: string[];
  generated_by: "model" | "deterministic_fallback" | string;
};

export type AiRunResult = {
  search: SingleSearchPayload | null;
  evidence: Record<string, unknown>;
  knowledge_hits?: KnowledgeHit[];
  searches?: Array<Record<string, unknown>>;
  summary: AiAnalysisSummary;
  provenance: {
    dataset_id: number;
    index_id: number;
    model_config_id: number;
    model_id: string;
    provider: string;
  };
};

export type AiRun = {
  id: number;
  conversation_id: number;
  intent: "single_cell_search" | "result_follow_up" | string;
  context_run_id: number | null;
  search_task_id: number | null;
  model: AiModelConfig | null;
  status: string;
  progress: number;
  stage: { key: string; label: string; state: string; message: string | null; started_at: string | null; completed_at: string | null } | null;
  timeline: Array<{ key: string; label: string; state: string; message: string | null; started_at: string | null; completed_at: string | null }>;
  summary_status: "not_started" | "pending" | "running" | "model" | "fallback" | string;
  summary_message: string | null;
  response_language: string;
  can_cancel: boolean;
  stream_url: string;
  poll_after_ms: number | null;
  plan: AiSearchPlan | AiAnalysisPlan | null;
  result: AiRunResult | null;
  error_code: string | null;
  error_message: string | null;
  can_manage: boolean;
  usage: { provider_requests: number; input_tokens: number; output_tokens: number; latency_ms: number };
  tool_call: { id: number; name: string; status: string; args: Record<string, unknown> } | null;
  tool_calls: Array<{ id: number; name: string; status: string; order_index: number; task_id: number | null; args: Record<string, unknown> }>;
  created_at: string | null;
  updated_at: string | null;
  completed_at: string | null;
};

export type SearchHistoryItem = {
  id: number;
  mode: "single" | "multi" | "joint";
  source: "query_lab" | "ai" | string;
  status: string;
  message: string | null;
  legacy: boolean;
  dataset_id: number | null;
  dataset_name: string | null;
  query_cell_index: number | null;
  top_k: number | null;
  result_count: number;
  query_time_ms: number | null;
  request: Record<string, unknown>;
  result?: SingleSearchPayload | MultiSearchPayload | JointSearchPayload | null;
  error?: string | null;
  ai_run_id: number | null;
  conversation_id: number | null;
  created_at: string | null;
  updated_at: string | null;
};

export type AiMessage = {
  id: number;
  role: "user" | "assistant" | string;
  content: string;
  structured: Record<string, unknown> | null;
  citations?: Array<{ key: string; source_title: string; heading: string | null; page_number: number | null; excerpt: string }>;
  created_at: string | null;
};

export type AiConversation = {
  id: number;
  title: string;
  created_at: string | null;
  updated_at: string | null;
  messages?: AiMessage[];
  runs?: AiRun[];
};

export type AiUsage = {
  totals: { runs: number; provider_requests: number; input_tokens: number; output_tokens: number; failed_runs: number; embedding_requests: number; provider_call_records: number };
  by_model: Array<Record<string, string | number | null>>;
  by_user: Array<Record<string, string | number | null>>;
  by_operation: Array<Record<string, string | number | null>>;
};

export type KnowledgeDocument = {
  id: number;
  scope: "platform" | "dataset" | "personal";
  owner_id: number | null;
  dataset_id: number | null;
  dataset_name: string | null;
  title: string;
  description: string;
  original_filename: string | null;
  mime_type: string | null;
  size_bytes: number;
  source_type: "upload" | "builtin" | string;
  source_key: string | null;
  version: string;
  status: string;
  semantic_status: string;
  page_count: number | null;
  chunk_count: number;
  error_message: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type KnowledgeHit = {
  key: string;
  chunk_id: number;
  document_id: number;
  title: string;
  scope: string;
  dataset_id: number | null;
  heading: string | null;
  page_number: number | null;
  excerpt: string;
  score: number;
};
