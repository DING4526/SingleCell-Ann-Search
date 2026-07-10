<template>
  <PageHeader title="联合索引" description="基于共同基因、PCA 与 Harmony 校正构建跨数据集物理 HNSW 索引。">
    <template #actions>
      <a-space wrap>
        <a-button @click="load">刷新</a-button>
        <a-button v-if="datasetOptions.length >= 2" type="primary" @click="drawerOpen = true">构建联合索引</a-button>
      </a-space>
    </template>
  </PageHeader>

  <section class="surface">
    <div class="toolbar">
      <div>
        <span class="toolbar-title">Harmony 联合索引</span>
        <div class="toolbar-subtitle">联合索引与单数据集算法选优相互独立。</div>
      </div>
    </div>
    <a-table :data-source="jointIndexes" :columns="columns" row-key="id" size="small" :pagination="false" :scroll="jointIndexes.length ? { x: 820 } : undefined">
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'status'"><StatusTag :status="record.status" /></template>
        <template v-else-if="column.key === 'datasets'">纳入 {{ includedCount(record) }} / 跳过 {{ skippedCount(record) }}</template>
      </template>
    </a-table>
  </section>

  <a-drawer v-model:open="drawerOpen" title="构建 Harmony 联合索引" width="520">
    <a-form layout="vertical">
      <a-alert message="将在共享校正空间中构建物理 HNSW 索引。" type="info" show-icon />
      <a-alert v-if="task" style="margin-top: 12px" :message="task.message" :type="task.status === 'error' ? 'error' : task.status === 'success' ? 'success' : 'info'" show-icon />
      <a-progress v-if="task" style="margin-top: 12px" :percent="task.progress || 0" :status="task.status === 'error' ? 'exception' : task.status === 'success' ? 'success' : 'active'" />
      <a-form-item label="名称" style="margin-top: 16px"><a-input v-model:value="form.name" /></a-form-item>
      <a-form-item label="数据集">
        <a-checkbox-group v-model:value="form.dataset_ids" class="dataset-list">
          <a-checkbox v-for="item in datasetOptions" :key="item.id" :value="item.id">{{ item.name }}（{{ item.n_cells || "?" }} 个细胞）</a-checkbox>
        </a-checkbox-group>
      </a-form-item>
      <a-form-item label="距离度量"><a-segmented v-model:value="form.metric" :options="metricOptions" /></a-form-item>
      <div class="field-grid">
        <a-form-item label="PCA 维度"><a-input-number v-model:value="form.n_pcs" :min="2" :max="200" /></a-form-item>
        <a-form-item label="高变基因"><a-input-number v-model:value="form.n_top_genes" :min="50" :max="10000" /></a-form-item>
        <a-form-item label="最少共同基因"><a-input-number v-model:value="form.min_common_genes" :min="1" :max="50000" /></a-form-item>
        <a-form-item label="M"><a-input-number v-model:value="form.M" :min="2" :max="128" /></a-form-item>
        <a-form-item label="ef_construction"><a-input-number v-model:value="form.ef_construction" :min="2" :max="1000" /></a-form-item>
        <a-form-item label="ef_search"><a-input-number v-model:value="form.ef_search" :min="1" :max="1000" /></a-form-item>
      </div>
      <a-button type="primary" block :loading="building" @click="build">构建联合索引</a-button>
    </a-form>
  </a-drawer>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { message } from "ant-design-vue";
import PageHeader from "@/components/PageHeader.vue";
import StatusTag from "@/components/StatusTag.vue";
import { api } from "@/services/api";
import { useDatasetStore } from "@/stores/datasets";
import { useTaskStore } from "@/stores/tasks";
import type { JointIndex, TaskRecord } from "@/types";

const store = useDatasetStore();
const taskStore = useTaskStore();
const jointIndexes = ref<JointIndex[]>([]);
const drawerOpen = ref(false);
const building = ref(false);
const task = ref<TaskRecord | null>(null);
const form = reactive({
  name: "Harmony 联合索引",
  dataset_ids: [] as number[],
  metric: "l2",
  M: 16,
  ef_construction: 200,
  ef_search: 100,
  n_pcs: 50,
  n_top_genes: 2000,
  min_common_genes: 500,
});
const metricOptions = [{ label: "L2", value: "l2" }, { label: "Cosine", value: "cosine" }];
const datasetOptions = computed(() => store.datasets.filter((item) => item.can_edit && ["processed", "indexed"].includes(item.status)));
const columns = [
  { title: "ID", dataIndex: "id", width: 64 },
  { title: "名称", dataIndex: "name" },
  { title: "度量", dataIndex: "metric", width: 80 },
  { title: "细胞", dataIndex: "n_cells", width: 100 },
  { title: "共同基因", dataIndex: "common_gene_count", width: 110 },
  { title: "数据集", key: "datasets", width: 150 },
  { title: "状态", key: "status", width: 90 },
];

function includedCount(record: JointIndex) { return record.datasets.filter((row) => row.status === "included").length; }
function skippedCount(record: JointIndex) { return record.datasets.filter((row) => row.status === "skipped").length; }

async function load() {
  const data = await api.jointIndexes();
  jointIndexes.value = data.joint_indexes;
}

async function build() {
  if (form.dataset_ids.length < 2) {
    message.warning("请至少选择两个数据集");
    return;
  }
  building.value = true;
  task.value = null;
  try {
    const data = await api.buildJointIndexTask(form);
    await taskStore.waitForTask(data.task_id, (next) => { task.value = next; }, { timeoutMs: 600_000 });
    await load();
    drawerOpen.value = false;
    message.success("联合索引构建完成");
  } catch (error) {
    message.error((error as Error).message);
  } finally {
    building.value = false;
  }
}

onMounted(async () => {
  await Promise.all([store.loadAll(), load()]);
  form.dataset_ids = datasetOptions.value.map((item) => item.id);
});
</script>

<style scoped>
.toolbar { padding: 16px; }
.toolbar-title { color: #172033; font-size: 15px; font-weight: 800; }
.toolbar-subtitle { margin-top: 3px; color: #64748b; font-size: 12px; }
.dataset-list { display: flex; flex-direction: column; gap: 6px; }
.field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 12px; }
.field-grid :deep(.ant-input-number) { width: 100%; }
@media (max-width: 640px) { .field-grid { grid-template-columns: 1fr; } }
</style>
