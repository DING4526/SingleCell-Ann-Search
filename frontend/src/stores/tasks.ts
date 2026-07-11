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
        if (!this.polling) return;
        try {
          await this.refreshActive();
        } catch {
          // A transient request failure must not create an unhandled promise;
          // the next scheduled poll will retry unless logout stopped polling.
        } finally {
          if (this.polling) activeTimer = window.setTimeout(tick, this.active.length ? 2500 : 12000);
        }
      };
      void tick();
    },
    stopActivePolling() {
      if (activeTimer) window.clearTimeout(activeTimer);
      activeTimer = undefined;
      this.polling = false;
    },
    async removeTask(taskId: number) {
      const result = await api.removeTask(taskId);
      this.recent = this.recent.filter((task) => task.id !== taskId);
      this.active = this.active.filter((task) => task.id !== taskId);
      return result;
    },
    async clearTerminalTasks() {
      const result = await api.clearTerminalTasks();
      await this.refreshRecent();
      return result.hidden_count ?? 0;
    },
    async waitForTask(taskId: number, onTick?: (task: TaskRecord) => void, options: { timeoutMs?: number; intervalMs?: number } = {}) {
      const startedAt = Date.now();
      const timeoutMs = options.timeoutMs ?? 0;
      const intervalMs = options.intervalMs ?? 1000;
      for (;;) {
        const task = await api.task(taskId);
        await this.refreshActive().catch(() => undefined);
        onTick?.(task);
        if (task.status === "success") {
          await this.refreshRecent().catch(() => undefined);
          return task;
        }
        if (["error", "cancelled"].includes(task.status)) {
          await this.refreshRecent().catch(() => undefined);
          throw new Error(task.error || task.message || (task.status === "cancelled" ? "任务已取消" : "任务失败"));
        }
        if (timeoutMs > 0 && Date.now() - startedAt > timeoutMs) {
          throw new Error(task.message ? `任务等待超时：${task.message}` : "任务等待超时");
        }
        await new Promise((resolve) => window.setTimeout(resolve, intervalMs));
      }
    },
  },
});
