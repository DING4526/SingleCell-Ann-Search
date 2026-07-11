import { defineStore } from "pinia";
import { api } from "@/services/api";
import type { Dataset, TaskRecord } from "@/types";

export const useDatasetStore = defineStore("datasets", {
  state: () => ({
    loading: false,
    datasets: [] as Dataset[],
    current: null as Dataset | null,
    stats: {} as Record<string, { name: string; count: number }[]>,
    recentTasks: [] as TaskRecord[],
  }),
  getters: {
    indexedDatasets: (state) => state.datasets.filter((dataset) => ["processed", "indexed"].includes(dataset.status)),
    readyIndexes: (state) => state.datasets.flatMap((dataset) => dataset.indexes.filter((idx) => idx.status === "ready" && idx.lifecycle === "active")),
  },
  actions: {
    async loadAll() {
      this.loading = true;
      try {
        const data = await api.datasets();
        this.datasets = data.datasets;
      } finally {
        this.loading = false;
      }
    },
    async loadDetail(id: number) {
      this.loading = true;
      try {
        const data = await api.dataset(id);
        this.current = data.dataset;
        this.stats = data.stats || {};
        this.recentTasks = data.recent_tasks || [];
        const index = this.datasets.findIndex((dataset) => dataset.id === id);
        if (index >= 0) this.datasets[index] = data.dataset;
      } finally {
        this.loading = false;
      }
    },
    async upload(form: FormData) {
      const data = await api.uploadDataset(form);
      await this.loadAll();
      return data.dataset_id;
    },
    async remove(id: number) {
      await api.deleteDataset(id);
      if (this.current?.id === id) this.current = null;
      await this.loadAll();
    },
  },
});
