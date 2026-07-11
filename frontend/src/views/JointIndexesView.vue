<template>
  <PageHeader title="联合索引" description="在统一校正空间中维护跨数据集索引，并清晰追踪数据组成与构建状态。">
    <template #actions>
      <a-space>
        <a-button :loading="loading" @click="load">刷新</a-button>
        <a-button v-if="datasetOptions.length >= 2" type="primary" @click="drawerOpen = true">构建联合索引</a-button>
      </a-space>
    </template>
  </PageHeader>

  <a-alert v-if="pageError" class="page-error" type="error" show-icon :message="pageError">
    <template #action><a-button size="small" @click="load">重新加载</a-button></template>
  </a-alert>

  <section class="surface table-shell">
    <div class="toolbar">
      <div>
        <div class="toolbar-title">联合索引记录</div>
        <div class="toolbar-subtitle">联合索引独立于单数据集索引，可按研究队列单独构建和删除。</div>
      </div>
      <span class="record-count">共 {{ jointIndexes.length }} 项</span>
    </div>
    <a-table
      class="compact-table joint-index-table"
      :loading="loading"
      :data-source="jointIndexes"
      :columns="columns"
      :pagination="jointIndexes.length > 10 ? { pageSize: 10 } : false"
      :locale="{ emptyText: '暂无联合索引' }"
      row-key="id"
      size="small"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'name'">
          <div class="primary-cell">
            <strong>{{ record.name }}</strong>
            <span>{{ formatDate(record.created_at) }}<template v-if="record.owner_name"> · {{ record.owner_name }}</template></span>
          </div>
        </template>
        <template v-else-if="column.key === 'datasets'">
          <div class="dataset-summary">
            <a-tag v-for="name in includedNames(record).slice(0, 2)" :key="name">{{ name }}</a-tag>
            <span v-if="includedNames(record).length > 2">另 {{ includedNames(record).length - 2 }} 个</span>
            <span v-if="skippedCount(record)" class="skipped-text">跳过 {{ skippedCount(record) }} 个</span>
          </div>
        </template>
        <template v-else-if="column.key === 'configuration'">
          <div class="secondary-stack">
            <strong>{{ metricText(record.metric) }}</strong>
            <span>PCA {{ record.n_pcs }} 维 · 图连接度 {{ record.M }}</span>
          </div>
        </template>
        <template v-else-if="column.key === 'scale'">
          <div class="secondary-stack numeric-cell">
            <strong>{{ formatCount(record.n_cells) }} 个细胞</strong>
            <span>{{ formatCount(record.common_gene_count) }} 个共同基因</span>
          </div>
        </template>
        <template v-else-if="column.key === 'status'">
          <div class="status-cell">
            <StatusTag :status="record.status" />
            <span v-if="record.error_message" class="error-summary" :title="record.error_message">{{ record.error_message }}</span>
            <span v-else-if="record.build_time_ms !== null" class="status-note">耗时 {{ formatMilliseconds(record.build_time_ms) }}</span>
          </div>
        </template>
        <template v-else-if="column.key === 'actions'">
          <a-space :size="4">
            <a-button v-if="record.status === 'ready'" type="link" size="small" @click="openQuery">用于检索</a-button>
            <a-button
              v-if="record.can_delete"
              type="link"
              danger
              size="small"
              :disabled="!!record.delete_blockers?.length"
              :title="record.delete_blockers?.join('；')"
              @click="confirmDelete(record)"
            >删除</a-button>
          </a-space>
        </template>
      </template>

      <template #expandedRowRender="{ record }">
        <div class="joint-details">
          <div>
            <strong>数据集组成</strong>
            <div class="dataset-detail-list">
              <span v-for="item in record.datasets" :key="item.dataset_id">
                <a-tag :color="item.status === 'included' ? 'success' : 'warning'">{{ item.status === 'included' ? '已纳入' : '已跳过' }}</a-tag>
                <b>{{ item.dataset_name || '未命名数据集' }}</b>
                <small>{{ formatCount(item.n_cells) }} 个细胞<template v-if="item.skip_reason"> · {{ item.skip_reason }}</template></small>
              </span>
            </div>
          </div>
          <div>
            <strong>构建参数</strong>
            <p>高变基因 {{ formatCount(record.n_top_genes) }} · 最少共同基因 {{ formatCount(record.min_common_genes) }} · 构建深度 {{ record.ef_construction }} · 检索深度 {{ record.ef_search }}</p>
          </div>
        </div>
      </template>
    </a-table>
  </section>

  <a-drawer v-model:open="drawerOpen" title="构建 Harmony 联合索引" width="640">
    <a-form layout="vertical">
      <a-alert message="平台将先对齐共同基因并进行 Harmony 校正，再构建跨数据集 HNSW 索引。" type="info" show-icon />
      <div v-if="task" class="build-progress">
        <div class="build-progress__head"><StatusTag :status="task.status" /><span>{{ task.error || task.message || '正在准备构建任务' }}</span></div>
        <a-progress :percent="task.progress || 0" :status="task.status === 'error' ? 'exception' : task.status === 'success' ? 'success' : 'active'" />
      </div>

      <section class="form-section">
        <div class="form-section__head"><strong>基础配置</strong><span>定义名称、参与数据和距离计算方式</span></div>
        <a-form-item label="索引名称" required><a-input v-model:value="form.name" placeholder="例如：肝脏队列联合索引" /></a-form-item>
        <a-form-item label="参与数据集" required extra="至少选择两个已完成预处理且有编辑权限的数据集">
          <a-checkbox-group v-model:value="form.dataset_ids" class="dataset-list">
            <a-checkbox v-for="item in datasetOptions" :key="item.id" :value="item.id">{{ item.name }}（{{ formatCount(item.n_cells || 0) }} 个细胞）</a-checkbox>
          </a-checkbox-group>
        </a-form-item>
        <div class="basic-grid">
          <a-form-item label="距离度量"><a-segmented v-model:value="form.metric" :options="metricOptions" /></a-form-item>
          <a-form-item label="PCA 维度"><a-input-number v-model:value="form.n_pcs" :min="2" :max="200" /></a-form-item>
        </div>
      </section>

      <a-collapse class="expert-section">
        <a-collapse-panel key="expert" header="专家配置">
          <a-alert class="expert-note" type="warning" show-icon message="默认值适用于大多数研究数据；调整前请确认数据规模与召回要求。" />
          <div class="field-grid">
            <a-form-item label="高变基因数"><a-input-number v-model:value="form.n_top_genes" :min="50" :max="10000" /></a-form-item>
            <a-form-item label="最少共同基因"><a-input-number v-model:value="form.min_common_genes" :min="1" :max="50000" /></a-form-item>
            <a-form-item label="图连接度（M）"><a-input-number v-model:value="form.M" :min="2" :max="128" /></a-form-item>
            <a-form-item label="构建搜索深度"><a-input-number v-model:value="form.ef_construction" :min="2" :max="1000" /></a-form-item>
            <a-form-item label="检索搜索深度"><a-input-number v-model:value="form.ef_search" :min="1" :max="1000" /></a-form-item>
          </div>
        </a-collapse-panel>
      </a-collapse>

      <a-button type="primary" block size="large" :loading="building" @click="build">开始构建</a-button>
    </a-form>
  </a-drawer>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { Modal, message } from "ant-design-vue";
import PageHeader from "@/components/PageHeader.vue";
import StatusTag from "@/components/StatusTag.vue";
import { api } from "@/services/api";
import { useDatasetStore } from "@/stores/datasets";
import { useTaskStore } from "@/stores/tasks";
import { formatDate, formatMilliseconds, metricText } from "@/utils/format";
import type { JointIndex, TaskRecord } from "@/types";

const router = useRouter();
const store = useDatasetStore();
const taskStore = useTaskStore();
const jointIndexes = ref<JointIndex[]>([]);
const drawerOpen = ref(false);
const loading = ref(false);
const pageError = ref("");
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
const metricOptions = [{ label: "L2 欧氏距离", value: "l2" }, { label: "余弦距离", value: "cosine" }];
const datasetOptions = computed(() => store.datasets.filter((item) => item.can_edit && ["processed", "indexed"].includes(item.status)));
const columns = [
  { title: "联合索引", key: "name", width: 180 },
  { title: "数据集", key: "datasets", width: 210 },
  { title: "配置摘要", key: "configuration", width: 200 },
  { title: "规模", key: "scale", width: 160 },
  { title: "状态", key: "status", width: 150 },
  { title: "操作", key: "actions", width: 130 },
];

function includedNames(record: JointIndex) {
  return record.datasets.filter((row) => row.status === "included").map((row) => row.dataset_name || "未命名数据集");
}
function skippedCount(record: JointIndex) { return record.datasets.filter((row) => row.status === "skipped").length; }
function formatCount(value?: number | null) { return Number(value || 0).toLocaleString("zh-CN"); }

async function load() {
  loading.value = true;
  pageError.value = "";
  try {
    jointIndexes.value = (await api.jointIndexes()).joint_indexes;
  } catch (error) {
    pageError.value = (error as Error).message;
  } finally {
    loading.value = false;
  }
}

function openQuery() {
  void router.push({ path: "/query-lab", query: { mode: "joint" } });
}

function confirmDelete(record: JointIndex) {
  Modal.confirm({
    title: `永久删除“${record.name}”？`,
    content: "联合索引文件及其检索历史将被移除，参与的数据集不会被删除。此操作不可撤销。",
    okText: "永久删除",
    okType: "danger",
    cancelText: "取消",
    async onOk() {
      try {
        await api.deleteJointIndex(record.id);
        await load();
        message.success("联合索引已删除");
      } catch (error) {
        message.error((error as Error).message);
        throw error;
      }
    },
  });
}

async function build() {
  if (!form.name.trim()) return message.warning("请输入索引名称");
  if (form.dataset_ids.length < 2) return message.warning("请至少选择两个数据集");
  building.value = true;
  task.value = null;
  try {
    const data = await api.buildJointIndexTask({ ...form, name: form.name.trim() });
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
.toolbar-subtitle { margin-top: 3px; color: #758297; font-size: 12px; }
.record-count { color: #8b97a8; font-size: 12px; }
.page-error { margin-bottom: 14px; }
.primary-cell, .secondary-stack, .status-cell { display: grid; gap: 3px; min-width: 0; }
.primary-cell strong, .secondary-stack strong { overflow: hidden; color: #2d3b50; text-overflow: ellipsis; white-space: nowrap; }
.primary-cell span, .secondary-stack span, .status-note { color: #7b899d; font-size: 11px; }
.dataset-summary { display: flex; align-items: center; gap: 4px; min-width: 0; flex-wrap: wrap; }
.dataset-summary :deep(.ant-tag) { max-width: 112px; margin-inline-end: 0; overflow: hidden; text-overflow: ellipsis; }
.dataset-summary > span { color: #77859a; font-size: 11px; }
.dataset-summary .skipped-text { color: #aa6a16; }
.numeric-cell { font-variant-numeric: tabular-nums; }
.error-summary { display: -webkit-box; overflow: hidden; color: #b33f3f; font-size: 11px; line-height: 1.4; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.joint-details { display: grid; grid-template-columns: 1.25fr .75fr; gap: 28px; padding: 6px 12px; }
.joint-details > div > strong { color: #344257; font-size: 12px; }
.joint-details p { margin: 8px 0 0; color: #66758c; font-size: 12px; line-height: 1.6; }
.dataset-detail-list { display: grid; gap: 6px; margin-top: 8px; }
.dataset-detail-list > span { display: grid; grid-template-columns: auto minmax(0, auto) 1fr; align-items: center; gap: 8px; }
.dataset-detail-list b { color: #46546a; font-size: 12px; }
.dataset-detail-list small { color: #7b899d; }
.build-progress { display: grid; gap: 8px; margin-top: 14px; padding: 12px; border: 1px solid #dfe7f0; border-radius: 8px; background: #f8fafc; }
.build-progress__head { display: flex; align-items: center; gap: 8px; color: #56657a; font-size: 12px; }
.form-section { margin-top: 20px; }
.form-section__head { display: grid; gap: 2px; margin-bottom: 14px; padding-bottom: 10px; border-bottom: 1px solid #edf0f4; }
.form-section__head strong { color: #2f3d52; }
.form-section__head span { color: #8390a3; font-size: 11px; }
.dataset-list { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; max-height: 190px; padding: 10px; overflow-y: auto; border: 1px solid #dfe5ed; border-radius: 8px; background: #fafbfd; }
.dataset-list :deep(.ant-checkbox-wrapper) { min-width: 0; margin-inline-start: 0; }
.basic-grid { display: grid; grid-template-columns: 1.35fr .65fr; gap: 12px; }
.basic-grid :deep(.ant-input-number), .field-grid :deep(.ant-input-number) { width: 100%; }
.expert-section { margin: 2px 0 18px; border-color: #dfe5ed; border-radius: 8px; }
.expert-note { margin-bottom: 14px; }
.field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 12px; }
</style>
