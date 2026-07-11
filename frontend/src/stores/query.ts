import { defineStore } from "pinia";
import { api } from "@/services/api";
import { useTaskStore } from "@/stores/tasks";
import type { EvalMetrics, JointSearchPayload, MultiSearchPayload, PlotlyPayload, SearchPlotPayload, SearchResult, SingleSearchPayload, TaskRecord } from "@/types";

export const useQueryStore = defineStore("query", {
  state: () => ({
    loading: false,
    plotLoading: false,
    plotError: "",
    plotTask: null as TaskRecord | null,
    searchRunId: 0,
    results: [] as SearchResult[],
    multiResults: [] as SearchResult[],
    jointResults: [] as SearchResult[],
    scatter: null as PlotlyPayload | null,
    evaluationPlot: null as PlotlyPayload | null,
    metrics: null as EvalMetrics | null,
    queryTimeMs: null as number | null,
    interpretation: {} as Record<string, unknown>,
    multiMeta: null as { searched_dataset_count: number; skipped: unknown[]; metric: string } | null,
    jointMeta: null as { joint_index_id: number; query_global_label: number; searched_dataset_count: number; metric: string } | null,
  }),
  actions: {
    resetSearchState() {
      this.searchRunId += 1;
      this.results = [];
      this.multiResults = [];
      this.jointResults = [];
      this.scatter = null;
      this.plotLoading = false;
      this.plotError = "";
      this.plotTask = null;
      this.queryTimeMs = null;
      this.interpretation = {};
      this.multiMeta = null;
      this.jointMeta = null;
    },
    applySingleSearchPayload(payload: SingleSearchPayload) {
      this.results = payload.result_data.results;
      this.queryTimeMs = payload.result_data.query_time_ms;
      this.scatter = payload.scatter_plot || null;
      this.interpretation = payload.interpretation || {};
      this.multiResults = [];
      this.multiMeta = null;
      this.jointResults = [];
      this.jointMeta = null;
    },
    applyMultiSearchPayload(payload: MultiSearchPayload) {
      this.multiResults = payload.result_data.results;
      this.queryTimeMs = payload.result_data.query_time_ms;
      this.results = [];
      this.jointResults = [];
      this.scatter = null;
      this.multiMeta = {
        searched_dataset_count: payload.result_data.searched_dataset_count,
        skipped: payload.result_data.skipped,
        metric: payload.result_data.metric,
      };
      this.jointMeta = null;
    },
    applyJointSearchPayload(payload: JointSearchPayload) {
      this.jointResults = payload.result_data.results;
      this.queryTimeMs = payload.result_data.query_time_ms;
      this.results = [];
      this.multiResults = [];
      this.scatter = null;
      this.multiMeta = null;
      this.jointMeta = {
        joint_index_id: payload.result_data.joint_index_id,
        query_global_label: payload.result_data.query_global_label,
        searched_dataset_count: payload.result_data.searched_dataset_count,
        metric: payload.result_data.metric,
      };
    },
    async runSearch(params: { dataset_id: number; index_id: number; query_cell_index: number; top_k: number; filter_cell_type?: string }, onTick?: (task: TaskRecord) => void) {
      this.loading = true;
      try {
        this.resetSearchState();
        const runId = this.searchRunId;
        const data = await api.searchTask(params);
        const task = await useTaskStore().waitForTask(data.task_id, onTick, { timeoutMs: 120_000 });
        this.applySingleSearchPayload(task.result as SingleSearchPayload);
        const resultCellIndices = this.results.map((row) => row.cell_index);
        if (resultCellIndices.length > 0) {
          void this.runSearchPlot({
            dataset_id: params.dataset_id,
            query_cell_index: params.query_cell_index,
            result_cell_indices: resultCellIndices,
          }, runId);
        }
      } finally {
        this.loading = false;
      }
    },
    async runSearchPlot(params: { dataset_id: number; query_cell_index: number; result_cell_indices: number[] }, expectedRunId?: number) {
      const runId = expectedRunId ?? this.searchRunId;
      this.plotLoading = true;
      this.plotError = "";
      this.plotTask = null;
      try {
        const data = await api.searchPlotTask({ ...params, max_background_points: 8_000 });
        const task = await useTaskStore().waitForTask(data.task_id, (nextTask) => {
          if (this.searchRunId === runId) this.plotTask = nextTask;
        }, { timeoutMs: 180_000 });
        if (this.searchRunId === runId) {
          const payload = task.result as SearchPlotPayload;
          this.scatter = payload.scatter_plot;
        }
      } catch (error) {
        if (this.searchRunId === runId) this.plotError = (error as Error).message;
      } finally {
        if (this.searchRunId === runId) this.plotLoading = false;
      }
    },
    async runMultiSearch(params: FormData, onTick?: (task: TaskRecord) => void) {
      this.loading = true;
      try {
        this.resetSearchState();
        const data = await api.multiSearchTask(params);
        const task = await useTaskStore().waitForTask(data.task_id, onTick, { timeoutMs: 120_000 });
        this.applyMultiSearchPayload(task.result as MultiSearchPayload);
      } finally {
        this.loading = false;
      }
    },
    async runJointSearch(params: { joint_index_id: number; query_dataset_id: number; query_cell_index: number; top_k: number }, onTick?: (task: TaskRecord) => void) {
      this.loading = true;
      try {
        this.resetSearchState();
        const runId = this.searchRunId;
        const data = await api.jointSearchTask(params);
        const task = await useTaskStore().waitForTask(data.task_id, onTick, { timeoutMs: 180_000 });
        this.applyJointSearchPayload(task.result as JointSearchPayload);
        const resultGlobalLabels = this.jointResults
          .map((row) => row.global_label)
          .filter((label): label is number => typeof label === "number");
        if (this.jointMeta && resultGlobalLabels.length > 0) {
          void this.runJointSearchPlot({
            joint_index_id: params.joint_index_id,
            query_global_label: this.jointMeta.query_global_label,
            result_global_labels: resultGlobalLabels,
          }, runId);
        }
      } finally {
        this.loading = false;
      }
    },
    async runJointSearchPlot(params: { joint_index_id: number; query_global_label: number; result_global_labels: number[] }, expectedRunId?: number) {
      const runId = expectedRunId ?? this.searchRunId;
      this.plotLoading = true;
      this.plotError = "";
      this.plotTask = null;
      try {
        const data = await api.jointSearchPlotTask({ ...params, max_background_points: 12_000 });
        const task = await useTaskStore().waitForTask(data.task_id, (nextTask) => {
          if (this.searchRunId === runId) this.plotTask = nextTask;
        }, { timeoutMs: 180_000 });
        if (this.searchRunId === runId) {
          const payload = task.result as SearchPlotPayload;
          this.scatter = payload.scatter_plot;
        }
      } catch (error) {
        if (this.searchRunId === runId) this.plotError = (error as Error).message;
      } finally {
        if (this.searchRunId === runId) this.plotLoading = false;
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
