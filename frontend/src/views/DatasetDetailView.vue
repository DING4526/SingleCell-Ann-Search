<template>
  <PageHeader :title="dataset?.name || '数据集详情'" :description="dataset?.description || '数据集资源详情、可视化、索引和任务记录。'">
    <template #actions>
      <a-space>
        <a-button @click="$router.push('/datasets')">返回列表</a-button>
        <a-button v-if="dataset?.status === 'uploaded' || dataset?.status === 'error'" type="primary" :loading="actionLoading" @click="process">处理数据集</a-button>
        <a-button v-if="dataset && ['processed', 'indexed'].includes(dataset.status)" type="primary" @click="$router.push(`/index-lab?dataset=${dataset.id}`)">构建索引</a-button>
        <a-button v-if="dataset?.ready_index_count" @click="$router.push(`/query-lab?dataset=${dataset.id}`)">检索细胞</a-button>
      </a-space>
    </template>
  </PageHeader>

  <a-spin :spinning="store.loading">
    <template v-if="dataset">
      <div class="metric-grid">
        <div class="metric-tile"><div class="metric-label">细胞数</div><div class="metric-value">{{ numberOrDash(dataset.n_cells) }}</div></div>
        <div class="metric-tile"><div class="metric-label">基因数</div><div class="metric-value">{{ numberOrDash(dataset.n_genes) }}</div></div>
        <div class="metric-tile"><div class="metric-label">PCA 维度</div><div class="metric-value">{{ numberOrDash(dataset.vector_dim) }}</div></div>
        <div class="metric-tile"><div class="metric-label">可用索引</div><div class="metric-value">{{ dataset.ready_index_count }}</div></div>
      </div>

      <div v-if="currentTask" class="surface surface-pad" style="margin-bottom: 18px">
        <div class="panel-title">当前任务</div>
        <a-alert
          :message="currentTask.message || '任务执行中...'"
          :description="currentTask.status === 'error' ? currentTask.error : undefined"
          :type="currentTask.status === 'error' ? 'error' : currentTask.status === 'success' ? 'success' : 'info'"
          show-icon
        />
        <a-progress style="margin-top: 12px" :percent="currentTask.progress || 0" :status="currentTask.status === 'error' ? 'exception' : currentTask.status === 'success' ? 'success' : 'active'" />
      </div>

      <div class="two-column">
        <div class="stack">
          <div class="surface surface-pad">
            <div class="panel-title">资源摘要</div>
            <a-descriptions :column="1" size="small" bordered>
              <a-descriptions-item label="状态"><StatusTag :status="dataset.status" /></a-descriptions-item>
              <a-descriptions-item label="访问范围">{{ dataset.owner_name || "旧数据" }} / {{ dataset.visibility }}</a-descriptions-item>
              <a-descriptions-item label="创建时间">{{ formatDate(dataset.created_at) }}</a-descriptions-item>
              <a-descriptions-item v-if="dataset.error_message" label="错误信息">{{ dataset.error_message }}</a-descriptions-item>
            </a-descriptions>
          </div>

          <div class="surface">
            <div class="toolbar"><span class="toolbar-title">细胞统计</span></div>
            <div class="surface-pad">
              <a-tabs>
                <a-tab-pane key="cell_type" tab="细胞类型"><StatList :rows="stats.cell_type || []" /></a-tab-pane>
                <a-tab-pane key="disease" tab="疾病"><StatList :rows="stats.disease || []" /></a-tab-pane>
                <a-tab-pane key="age_group" tab="年龄组"><StatList :rows="stats.age_group || []" /></a-tab-pane>
              </a-tabs>
            </div>
          </div>

          <div class="surface">
            <div class="toolbar"><span class="toolbar-title">最近任务</span></div>
            <a-list :data-source="store.recentTasks" size="small">
              <template #renderItem="{ item }">
                <a-list-item>
                  <a-list-item-meta :title="taskTypeText(item.type)" :description="item.message || item.error || '-'">
                    <template #avatar><StatusTag :status="item.status" /></template>
                  </a-list-item-meta>
                </a-list-item>
              </template>
            </a-list>
          </div>
        </div>

        <div class="stack">
          <div class="surface">
            <div class="toolbar">
              <span class="toolbar-title">嵌入图</span>
              <a-button size="small" :disabled="!canPlot" :loading="plotLoading" @click="loadScatter">重新加载</a-button>
            </div>
            <div class="surface-pad">
              <a-alert v-if="plotError" style="margin-bottom: 12px" type="error" show-icon :message="plotError" />
              <PlotlyPanel v-if="scatter" :payload="scatter" />
              <div v-else class="placeholder-panel">{{ canPlot ? "加载细胞分布图" : "处理数据集后可查看 UMAP/PCA 分布" }}</div>
            </div>
          </div>

          <div class="surface">
            <div class="toolbar">
              <span class="toolbar-title">索引</span>
              <a-button size="small" type="primary" :disabled="!['processed', 'indexed'].includes(dataset.status)" @click="$router.push(`/index-lab?dataset=${dataset.id}`)">索引实验室</a-button>
            </div>
            <a-table :data-source="dataset.indexes" :columns="indexColumns" row-key="id" size="small" :pagination="false">
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'status'"><StatusTag :status="record.status" /></template>
              </template>
            </a-table>
          </div>
        </div>
      </div>
    </template>
  </a-spin>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { message } from "ant-design-vue";
import PageHeader from "@/components/PageHeader.vue";
import PlotlyPanel from "@/components/PlotlyPanel.vue";
import StatusTag from "@/components/StatusTag.vue";
import { api } from "@/services/api";
import { useDatasetStore } from "@/stores/datasets";
import { useTaskStore } from "@/stores/tasks";
import { formatDate, numberOrDash, taskTypeText } from "@/utils/format";
import type { PlotlyPayload, TaskRecord } from "@/types";

const route = useRoute();
const store = useDatasetStore();
const taskStore = useTaskStore();
const actionLoading = ref(false);
const plotLoading = ref(false);
const plotError = ref("");
const currentTask = ref<TaskRecord | null>(null);
const scatter = ref<PlotlyPayload | null>(null);
const datasetId = computed(() => Number(route.params.id));
const dataset = computed(() => store.current);
const stats = computed(() => store.stats);
const canPlot = computed(() => !!dataset.value && ["processed", "indexed"].includes(dataset.value.status));

const indexColumns = [
  { title: "算法", dataIndex: "algorithm", width: 110 },
  { title: "距离度量", dataIndex: "metric", width: 90 },
  { title: "M", dataIndex: "M", width: 70 },
  { title: "ef", dataIndex: "ef_search", width: 80 },
  { title: "构建耗时 ms", dataIndex: "build_time_ms", width: 120 },
  { title: "状态", key: "status", width: 100 },
];

const StatList = defineComponent({
  props: { rows: { type: Array, required: true } },
  setup(props) {
    return () => {
      const rows = props.rows as { name: string; count: number }[];
      if (!rows.length) return h("div", { class: "muted" }, "暂无统计数据");
      const max = Math.max(...rows.map((row) => row.count), 1);
      return h("div", { class: "stack" }, rows.slice(0, 10).map((row) =>
        h("div", { style: "display:grid;grid-template-columns:150px 1fr 64px;gap:10px;align-items:center;font-size:13px;" }, [
          h("span", { title: row.name, style: "overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" }, row.name),
          h("div", { style: "height:8px;background:#e8eef6;border-radius:999px;overflow:hidden;" }, [
            h("div", { style: `width:${Math.round((row.count / max) * 100)}%;height:100%;background:#2563eb;` }),
          ]),
          h("span", { class: "muted", style: "text-align:right;" }, row.count),
        ]),
      ));
    };
  },
});

async function reload() {
  await store.loadDetail(datasetId.value);
  if (canPlot.value) loadScatter();
}

async function loadScatter() {
  if (!canPlot.value) return;
  plotLoading.value = true;
  plotError.value = "";
  try {
    const data = await api.scatter(datasetId.value);
    scatter.value = data.scatter_plot;
  } catch (error) {
    plotError.value = (error as Error).message;
    message.error(plotError.value);
  } finally {
    plotLoading.value = false;
  }
}

async function process() {
  actionLoading.value = true;
  currentTask.value = null;
  try {
    const data = await api.processDataset(datasetId.value);
    await taskStore.waitForTask(data.task_id, (task) => {
      currentTask.value = task;
    });
    message.success("数据集处理完成");
    await reload();
  } catch (error) {
    message.error((error as Error).message);
  } finally {
    actionLoading.value = false;
  }
}

onMounted(reload);
</script>
