import { defineStore } from "pinia";
import { api } from "@/services/api";
import type { EvalMetrics, PlotlyPayload, SearchResult } from "@/types";

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
    async runSearch(params: { dataset_id: number; index_id: number; query_cell_index: number; top_k: number; filter_cell_type?: string }) {
      this.loading = true;
      try {
        this.results = [];
        this.multiResults = [];
        this.scatter = null;
        this.queryTimeMs = null;
        this.multiMeta = null;
        const data = await api.search(params);
        this.results = data.result_data.results;
        this.queryTimeMs = data.result_data.query_time_ms;
        this.scatter = data.scatter_plot;
        this.interpretation = data.interpretation || {};
      } finally {
        this.loading = false;
      }
    },
    async runMultiSearch(params: FormData) {
      this.loading = true;
      try {
        this.results = [];
        this.multiResults = [];
        this.scatter = null;
        this.queryTimeMs = null;
        const data = await api.multiSearch(params);
        this.multiResults = data.result_data.results;
        this.queryTimeMs = data.result_data.query_time_ms;
        this.multiMeta = {
          searched_dataset_count: data.result_data.searched_dataset_count,
          skipped: data.result_data.skipped,
          metric: data.result_data.metric,
        };
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
