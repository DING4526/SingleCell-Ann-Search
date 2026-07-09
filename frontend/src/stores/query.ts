import { defineStore } from "pinia";
import { api } from "@/services/api";
import { useTaskStore } from "@/stores/tasks";
import type { EvalMetrics, MultiSearchPayload, PlotlyPayload, SearchResult, SingleSearchPayload, TaskRecord } from "@/types";

export const useQueryStore = defineStore("query", {
  state: () => ({
    loading: false,
    results: [] as SearchResult[],
    multiResults: [] as SearchResult[],
    scatter: null as PlotlyPayload | null,
    evaluationPlot: null as PlotlyPayload | null,
    metrics: null as EvalMetrics | null,
    queryTimeMs: null as number | null,
    interpretation: {} as Record<string, unknown>,
    multiMeta: null as { searched_dataset_count: number; skipped: unknown[]; metric: string } | null,
  }),
  actions: {
    resetSearchState() {
      this.results = [];
      this.multiResults = [];
      this.scatter = null;
      this.queryTimeMs = null;
      this.interpretation = {};
      this.multiMeta = null;
    },
    applySingleSearchPayload(payload: SingleSearchPayload) {
      this.results = payload.result_data.results;
      this.queryTimeMs = payload.result_data.query_time_ms;
      this.scatter = payload.scatter_plot;
      this.interpretation = payload.interpretation || {};
      this.multiResults = [];
      this.multiMeta = null;
    },
    applyMultiSearchPayload(payload: MultiSearchPayload) {
      this.multiResults = payload.result_data.results;
      this.queryTimeMs = payload.result_data.query_time_ms;
      this.results = [];
      this.scatter = null;
      this.multiMeta = {
        searched_dataset_count: payload.result_data.searched_dataset_count,
        skipped: payload.result_data.skipped,
        metric: payload.result_data.metric,
      };
    },
    async runSearch(params: { dataset_id: number; index_id: number; query_cell_index: number; top_k: number; filter_cell_type?: string }, onTick?: (task: TaskRecord) => void) {
      this.loading = true;
      try {
        this.resetSearchState();
        const data = await api.searchTask({ ...params, max_background_points: 15_000 });
        const task = await useTaskStore().waitForTask(data.task_id, onTick);
        this.applySingleSearchPayload(task.result as SingleSearchPayload);
      } finally {
        this.loading = false;
      }
    },
    async runMultiSearch(params: FormData, onTick?: (task: TaskRecord) => void) {
      this.loading = true;
      try {
        this.resetSearchState();
        const data = await api.multiSearchTask(params);
        const task = await useTaskStore().waitForTask(data.task_id, onTick);
        this.applyMultiSearchPayload(task.result as MultiSearchPayload);
      } finally {
        this.loading = false;
      }
    },
    async evaluate(params: { dataset_id: number; index_id: number; sample_size: number; eval_top_k: number }) {
      this.loading = true;
      try {
        const data = await api.evaluate(params);
        this.metrics = data.metrics;
        this.evaluationPlot = data.bar_plot;
      } finally {
        this.loading = false;
      }
    },
  },
});
