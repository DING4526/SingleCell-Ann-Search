<template>
  <PageHeader title="Index Lab" description="构建和管理索引实验。当前启用 HNSW，预留多算法、参数实验和合并索引能力。">
    <template #actions>
      <a-space>
        <a-select v-model:value="selectedDatasetId" style="width: 280px" placeholder="选择数据集" :options="datasetOptions" @change="loadDetail" />
        <a-button type="primary" :disabled="!canBuild" @click="drawerOpen = true">构建索引</a-button>
      </a-space>
    </template>
  </PageHeader>

  <div class="metric-grid">
    <div class="metric-tile"><div class="metric-label">Dataset Status</div><div class="metric-value small-value">{{ dataset?.status || "-" }}</div></div>
    <div class="metric-tile"><div class="metric-label">Vector Dim</div><div class="metric-value">{{ numberOrDash(dataset?.vector_dim) }}</div></div>
    <div class="metric-tile"><div class="metric-label">Ready Indexes</div><div class="metric-value">{{ dataset?.ready_index_count || 0 }}</div></div>
    <div class="metric-tile"><div class="metric-label">Algorithms</div><div class="metric-value small-value">HNSW + planned</div></div>
  </div>

  <div class="two-column">
    <div class="surface">
      <div class="toolbar"><span class="toolbar-title">Index Inventory</span></div>
      <a-table :data-source="dataset?.indexes || []" :columns="columns" row-key="id" size="middle" :pagination="false">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'status'"><StatusTag :status="record.status" /></template>
        </template>
      </a-table>
    </div>

    <div class="surface">
      <div class="toolbar"><span class="toolbar-title">Algorithm Roadmap</span></div>
      <div class="surface-pad capability-list">
        <div v-for="capability in indexCapabilities" :key="capability.key" class="capability-card">
          <a-tag :color="capability.status === 'ready' ? 'green' : 'default'">{{ capability.status }}</a-tag>
          <h3>{{ capability.title }}</h3>
          <p class="muted">{{ capability.description }}</p>
        </div>
      </div>
    </div>
  </div>

  <a-drawer v-model:open="drawerOpen" title="Build HNSW Index" width="460">
    <a-form layout="vertical" @finish="build">
      <a-alert message="当前实现为 HNSW baseline；多算法切换会接入同一构建面板。" type="info" show-icon />
      <a-form-item label="Distance Metric" style="margin-top: 16px">
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
      <a-button type="primary" html-type="submit" block :loading="building">构建索引</a-button>
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
import { numberOrDash } from "@/utils/format";

const route = useRoute();
const store = useDatasetStore();
const taskStore = useTaskStore();
const selectedDatasetId = ref<number | undefined>(undefined);
const drawerOpen = ref(false);
const building = ref(false);
const form = reactive({ metric: "l2", M: 16, ef_construction: 200, ef_search: 100 });
const dataset = computed(() => store.current);
const canBuild = computed(() => !!dataset.value && ["processed", "indexed"].includes(dataset.value.status));
const datasetOptions = computed(() => store.datasets.map((dataset) => ({ value: dataset.id, label: `${dataset.name} (${dataset.status})` })));
const indexCapabilities = capabilities.filter((capability) => ["hnsw", "merged-index", "multi-algorithm"].includes(capability.key));
const columns = [
  { title: "ID", dataIndex: "id", width: 70 },
  { title: "Algorithm", dataIndex: "algorithm" },
  { title: "Metric", dataIndex: "metric" },
  { title: "M", dataIndex: "M" },
  { title: "ef_search", dataIndex: "ef_search" },
  { title: "Build ms", dataIndex: "build_time_ms" },
  { title: "Status", key: "status" },
];

async function loadDetail() {
  if (!selectedDatasetId.value) return;
  await store.loadDetail(selectedDatasetId.value);
}

async function build() {
  if (!selectedDatasetId.value) return;
  building.value = true;
  try {
    const data = await api.buildIndex(selectedDatasetId.value, form);
    await taskStore.waitForTask(data.task_id);
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
