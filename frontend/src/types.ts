export type User = {
  id: number;
  username: string;
  role: "user" | "admin" | string;
  is_admin: boolean;
  is_enabled: boolean;
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
