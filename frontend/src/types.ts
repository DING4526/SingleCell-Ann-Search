export type User = {
  id: number;
  username: string;
  role: "user" | "admin" | string;
  is_admin: boolean;
};

export type AnnIndex = {
  id: number;
  dataset_id: number;
  algorithm: string;
  metric: "l2" | "cosine" | string;
  M: number;
  ef_construction: number;
  ef_search: number;
  build_time_ms: number | null;
  status: "building" | "ready" | "error" | string;
  created_at: string | null;
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
  dataset_id: number | null;
  dataset_name: string | null;
  updated_at: string | null;
};

export type SearchResult = {
  rank: number;
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
  avg_exact_time_ms: number;
  speedup: number;
  sample_size: number;
  top_k: number;
};

export type SingleSearchPayload = {
  result_data: {
    results: SearchResult[];
    query_time_ms: number;
    query_cell_index: number;
    top_k: number;
  };
  scatter_plot: PlotlyPayload;
  interpretation: Record<string, unknown>;
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
