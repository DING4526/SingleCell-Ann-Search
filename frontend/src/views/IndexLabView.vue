<template>
  <PageHeader title="索引实验室" description="构建和管理索引实验。当前启用 HNSW，预留多算法、参数实验和合并索引能力。">
    <template #actions>
      <a-space>
        <a-select v-model:value="selectedDatasetId" style="width: 280px" placeholder="选择数据集" :options="datasetOptions" @change="loadDetail" />
        <a-button type="primary" :disabled="!canBuild" @click="drawerOpen = true">构建索引</a-button>
      </a-space>
    </template>
  </PageHeader>

  <div class="metric-grid">
    <div class="metric-tile"><div class="metric-label">数据集状态</div><div class="metric-value small-value">{{ dataset ? statusText(dataset.status) : "-" }}</div></div>
    <div class="metric-tile"><div class="metric-label">向量维度</div><div class="metric-value">{{ numberOrDash(dataset?.vector_dim) }}</div></div>
    <div class="metric-tile"><div class="metric-label">可用索引</div><div class="metric-value">{{ dataset?.ready_index_count || 0 }}</div></div>
    <div class="metric-tile"><div class="metric-label">算法能力</div><div class="metric-value small-value">HNSW + 规划中</div></div>
  </div>

  <div class="two-column">
    <div class="surface">
      <div class="toolbar"><span class="toolbar-title">索引清单</span></div>
      <a-table :data-source="dataset?.indexes || []" :columns="columns" row-key="id" size="middle" :pagination="false">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'status'"><StatusTag :status="record.status" /></template>
        </template>
      </a-table>
    </div>

    <div class="surface">
      <div class="toolbar"><span class="toolbar-title">算法路线图</span></div>
      <div class="surface-pad capability-list">
        <div v-for="capability in indexCapabilities" :key="capability.key" class="capability-card">
          <a-tag :color="capability.status === 'ready' ? 'green' : 'default'">{{ statusText(capability.status) }}</a-tag>
          <h3>{{ capability.title }}</h3>
          <p class="muted">{{ capability.description }}</p>
        </div>
      </div>
    </div>
  </div>

  <a-drawer v-model:open="drawerOpen" title="构建 HNSW 索引" width="460">
    <a-form layout="vertical">
      <a-alert message="当前实现为 HNSW baseline；多算法切换会接入同一构建面板。" type="info" show-icon />
      <a-alert
        v-if="currentTask"
        style="margin-top: 12px"
        :message="currentTask.message || '任务执行中...'"
        :type="currentTask.status === 'error' ? 'error' : currentTask.status === 'success' ? 'success' : 'info'"
        show-icon
      />
      <a-progress v-if="currentTask" style="margin-top: 12px" :percent="currentTask.progress || 0" :status="currentTask.status === 'error' ? 'exception' : currentTask.status === 'success' ? 'success' : 'active'" />
      <a-form-item label="距离度量" style="margin-top: 16px">
        <a-segmented v-model:value="form.metric" :options="['l2', 'cosine']" />
      </a-form-item>
      <a-form-item label="M">
        <a-input-number v-model:value="form.M" :min="2" :max="128" style="width: 100%" />
      </a-form-item>
      <a-form-item label="ef_construction">
        <a-input-number v-model:value="form.ef_construction" :min="2" :max="1000" style="width: 100%" />
      </a-form-item>
      <a-form-item label="ef_search">
        <a-input-number v-model:value="form.ef_search" :min="1" :max="1000" style="width: 100%" />
      </a-form-item>
      <a-button type="primary" block :loading="building" @click="build">构建索引</a-button>
    </a-form>
  </a-drawer>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRoute } from "vue-router";
import { message } from "ant-design-vue";
import PageHeader from "@/components/PageHeader.vue";
import StatusTag from "@/components/StatusTag.vue";
import { api } from "@/services/api";
import { capabilities } from "@/services/capabilities";
import { useDatasetStore } from "@/stores/datasets";
import { useTaskStore } from "@/stores/tasks";
import { numberOrDash, statusText } from "@/utils/format";
import type { TaskRecord } from "@/types";

const route = useRoute();
const store = useDatasetStore();
const taskStore = useTaskStore();
const selectedDatasetId = ref<number | undefined>(undefined);
const drawerOpen = ref(false);
const building = ref(false);
const currentTask = ref<TaskRecord | null>(null);
const form = reactive({ metric: "l2", M: 16, ef_construction: 200, ef_search: 100 });
const dataset = computed(() => store.current);
const canBuild = computed(() => !!dataset.value && ["processed", "indexed"].includes(dataset.value.status));
const datasetOptions = computed(() => store.datasets.map((dataset) => ({ value: dataset.id, label: `${dataset.name}（${statusText(dataset.status)}）` })));
const indexCapabilities = capabilities.filter((capability) => ["hnsw", "merged-index", "multi-algorithm"].includes(capability.key));
const columns = [
  { title: "ID", dataIndex: "id", width: 70 },
  { title: "算法", dataIndex: "algorithm" },
  { title: "距离度量", dataIndex: "metric" },
  { title: "M", dataIndex: "M" },
  { title: "ef_search", dataIndex: "ef_search" },
  { title: "构建耗时 ms", dataIndex: "build_time_ms" },
  { title: "状态", key: "status" },
];

async function loadDetail() {
  if (!selectedDatasetId.value) return;
  await store.loadDetail(selectedDatasetId.value);
}

async function build() {
  if (!selectedDatasetId.value) return;
  building.value = true;
  currentTask.value = null;
  try {
    const data = await api.buildIndex(selectedDatasetId.value, form);
    await taskStore.waitForTask(data.task_id, (task) => {
      currentTask.value = task;
    });
    message.success("索引构建完成");
    drawerOpen.value = false;
    await loadDetail();
  } catch (error) {
    message.error((error as Error).message);
  } finally {
    building.value = false;
  }
}

onMounted(async () => {
  await store.loadAll();
  selectedDatasetId.value = Number(route.query.dataset) || store.datasets[0]?.id;
  await loadDetail();
});
</script>

<style scoped>
.small-value {
  font-size: 18px;
}
</style>
