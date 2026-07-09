import { defineStore } from "pinia";
import { api } from "@/services/api";
import type { TaskRecord } from "@/types";

let activeTimer: number | undefined;

export const useTaskStore = defineStore("tasks", {
  state: () => ({
    active: [] as TaskRecord[],
    recent: [] as TaskRecord[],
    polling: false,
  }),
  actions: {
    async refreshActive() {
      const data = await api.activeTasks();
      this.active = data.tasks;
    },
    async refreshRecent(status = "all") {
      const data = await api.tasks(status, 30);
      this.recent = data.tasks;
    },
    startActivePolling() {
      if (activeTimer) return;
      this.polling = true;
      const tick = async () => {
        try {
          await this.refreshActive();
        } finally {
          activeTimer = window.setTimeout(tick, this.active.length ? 2000 : 12000);
        }
      };
      tick();
    },
    stopActivePolling() {
      if (activeTimer) window.clearTimeout(activeTimer);
      activeTimer = undefined;
      this.polling = false;
    },
    async waitForTask(taskId: number, onTick?: (task: TaskRecord) => void) {
      for (;;) {
        const task = await api.task(taskId);
        onTick?.(task);
        if (task.status === "success") return task;
        if (task.status === "error") throw new Error(task.error || task.message || "任务失败");
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
      }
    },
  },
});
