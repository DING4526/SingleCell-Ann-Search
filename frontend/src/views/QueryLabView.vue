<template>
  <PageHeader title="检索实验室" description="执行单数据集、fan-out 跨数据集或 Harmony 联合索引检索。">
    <template #actions>
      <a-space wrap>
        <a-button @click="openHistoryDrawer">检索历史</a-button>
        <a-segmented
          v-model:value="mode"
          :options="[
            { label: '单数据集', value: 'single' },
            { label: 'Fan-out', value: 'multi' },
            { label: '联合索引', value: 'joint' },
          ]"
          @change="onModeChange"
        />
      </a-space>
    </template>
  </PageHeader>

  <div class="query-workbench">
    <div class="surface surface-pad query-panel">
      <div class="panel-title">检索条件</div>
      <p class="panel-help">选择检索空间和查询细胞，结果会保留在检索历史中。</p>
      <a-form layout="vertical">
        <template v-if="mode === 'joint'">
          <a-form-item label="联合索引">
            <a-select v-model:value="jointIndexId" :options="jointIndexOptions" placeholder="选择可用联合索引" @change="onJointIndexChange" />
          </a-form-item>
          <a-form-item label="查询数据集">
            <a-select v-model:value="datasetId" :options="jointDatasetOptions" placeholder="选择已纳入的数据集" />
          </a-form-item>
        </template>
        <template v-else>
          <a-form-item label="数据集">
            <a-select v-model:value="datasetId" :options="datasetOptions" placeholder="选择数据集" @change="onDatasetChange" />
          </a-form-item>
          <a-form-item label="索引">
            <a-select v-model:value="indexId" :options="indexOptions" placeholder="选择可用索引" />
          </a-form-item>
        </template>

        <a-form-item label="查询细胞编号">
          <a-input-number v-model:value="queryCellIndex" :min="0" :max="selectedDataset?.n_cells ? selectedDataset.n_cells - 1 : undefined" style="width: 100%" />
          <div class="field-help">可输入范围：0–{{ selectedDataset?.n_cells ? (selectedDataset.n_cells - 1).toLocaleString('zh-CN') : "待选择数据集" }}</div>
        </a-form-item>
        <a-form-item label="Top-K">
          <a-input-number v-model:value="topK" :min="1" :max="100" style="width: 100%" />
        </a-form-item>
        <a-form-item v-if="mode === 'single'" label="细胞类型过滤">
          <a-select v-model:value="cellType" allow-clear placeholder="全部细胞类型" :options="cellTypeOptions" />
        </a-form-item>
        <a-form-item v-if="mode === 'multi'" label="目标数据集">
          <a-checkbox-group v-model:value="targetDatasetIds" class="dataset-check-list">
            <a-checkbox v-for="dataset in store.indexedDatasets" :key="dataset.id" :value="dataset.id">{{ dataset.name }}</a-checkbox>
          </a-checkbox-group>
        </a-form-item>
        <a-button type="primary" block :loading="queryStore.loading" @click="run">运行检索</a-button>
        <div v-if="currentTask" class="task-inline">
          <a-alert
            :message="currentTask.message || '检索任务执行中...'"
            :type="currentTask.status === 'error' ? 'error' : currentTask.status === 'success' ? 'success' : 'info'"
            show-icon
          />
          <a-progress
            style="margin-top: 10px"
            :percent="currentTask.progress || 0"
            :status="currentTask.status === 'error' ? 'exception' : currentTask.status === 'success' ? 'success' : 'active'"
          />
        </div>
      </a-form>
    </div>

    <div class="stack">
      <div class="surface">
        <div class="toolbar">
          <span class="toolbar-title">检索结果</span>
          <a-space>
            <a-tag v-if="queryStore.queryTimeMs !== null">耗时 {{ formatMilliseconds(queryStore.queryTimeMs) }}</a-tag>
            <a-tag v-if="mode === 'multi' && queryStore.multiMeta">检索 {{ queryStore.multiMeta.searched_dataset_count }} 个数据集</a-tag>
            <a-tag v-if="mode === 'joint' && queryStore.jointMeta">联合索引 · {{ metricText(queryStore.jointMeta.metric) }}</a-tag>
            <a-tag>{{ activeResults.length }} 个细胞</a-tag>
          </a-space>
        </div>
        <div v-if="queryError" class="surface-pad" style="padding-bottom:0">
          <a-alert type="error" show-icon :message="queryError" />
        </div>
        <div class="table-shell">
          <a-table
            class="result-table compact-table"
            :data-source="activeResults"
            :columns="resultColumns"
            row-key="rank"
            size="small"
            :scroll="resultTableScroll"
            :pagination="false"
            :locale="{ emptyText: '运行检索后将在这里显示相似细胞' }"
          >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'rank'">
              <span class="rank-cell">{{ record.rank }}</span>
            </template>
            <template v-if="column.key === 'cell'">
              <div class="cell-primary" :title="record.cell_name">{{ record.cell_name || '未命名细胞' }}</div>
              <div class="cell-secondary">
                <span>{{ record.dataset_name || selectedDataset?.name || '未知数据集' }}</span>
                <span>细胞编号 {{ Number(record.cell_index).toLocaleString('zh-CN') }}</span>
                <span>{{ record.cell_type || '类型未知' }}</span>
              </div>
            </template>
            <template v-if="column.key === 'distance'">
              <span class="numeric-cell">{{ formatDistance(record.distance) }}</span>
            </template>
            <template v-if="column.key === 'metadata'">
              <div class="metadata-cell">
                <span>{{ record.disease || '疾病未知' }}</span>
                <span>{{ record.age_group || '年龄组未知' }}</span>
              </div>
            </template>
            <template v-if="column.key === 'actions'">
              <a-button size="small" @click="openCellDetail(record)">详情</a-button>
            </template>
          </template>
          </a-table>
        </div>
      </div>

      <div class="surface">
        <div class="toolbar"><span class="toolbar-title">嵌入空间高亮</span></div>
        <div class="plot-surface">
          <PlotlyPanel v-if="queryStore.scatter && mode !== 'multi'" :payload="queryStore.scatter" :interactive="true" :height="470" aria-label="检索结果在嵌入空间中的分布" />
          <div v-else-if="mode !== 'multi' && queryStore.plotLoading" class="placeholder-panel">
            <a-space direction="vertical" style="width: min(520px, 100%)">
              <a-alert
                :message="queryStore.plotTask?.message || '检索结果已显示，正在异步生成高亮图...'"
                type="info"
                show-icon
              />
              <a-progress
                :percent="queryStore.plotTask?.progress || 0"
                :status="queryStore.plotTask?.status === 'error' ? 'exception' : 'active'"
              />
            </a-space>
          </div>
          <div v-else-if="mode !== 'multi' && queryStore.plotError" class="placeholder-panel">
            <a-alert type="warning" show-icon :message="queryStore.plotError" />
          </div>
          <div v-else class="placeholder-panel">
            {{ placeholderText }}
          </div>
        </div>
      </div>
    </div>
  </div>

  <a-drawer v-model:open="historyOpen" title="检索历史" width="min(680px, 96vw)">
    <a-space wrap class="history-filters">
      <a-select v-model:value="historyFilters.mode" style="width:130px" :options="historyModeOptions" @change="loadHistory" />
      <a-select v-model:value="historyFilters.source" style="width:130px" :options="historySourceOptions" @change="loadHistory" />
      <a-select v-model:value="historyFilters.status" style="width:130px" :options="historyStatusOptions" @change="loadHistory" />
      <a-button @click="loadHistory">刷新</a-button>
      <a-popconfirm title="从列表移除当前筛选下的全部已完成历史？" @confirm="clearHistory">
        <a-button danger ghost>清空筛选结果</a-button>
      </a-popconfirm>
    </a-space>
    <a-list :data-source="historyItems" :loading="historyLoading" item-layout="vertical">
      <template #renderItem="{ item }">
        <a-list-item>
          <div class="history-record">
            <div class="history-title">
              <strong>{{ item.dataset_name || '跨数据集检索' }} · 细胞编号 {{ formatCellIndex(item.query_cell_index) }}</strong>
              <a-space wrap>
                <a-tag>{{ historyModeLabel(item.mode) }}</a-tag>
                <a-tag :color="item.source === 'ai' ? 'purple' : 'blue'">{{ item.source === 'ai' ? 'AI' : '人工' }}</a-tag>
                <a-tag :color="item.status === 'success' ? 'green' : item.status === 'error' ? 'red' : 'blue'">{{ statusText(item.status) }}</a-tag>
              </a-space>
            </div>
            <div class="history-meta">Top-K {{ item.top_k ?? '-' }} · 返回 {{ item.result_count }} 个细胞 · {{ formatMilliseconds(item.query_time_ms) }} · {{ formatDate(item.updated_at) }}</div>
            <a-alert v-if="item.legacy" type="warning" show-icon message="旧记录缺少完整索引参数；可查看结果，重新运行前需选择有效索引。" />
            <a-space wrap style="margin-top:10px">
              <a-button type="primary" size="small" :disabled="item.status !== 'success'" @click="selectHistory(item.id)">载入结果</a-button>
              <a-button v-if="item.conversation_id" size="small" @click="openAiConversation(item.conversation_id)">查看 AI 会话</a-button>
              <a-popconfirm title="从历史列表移除此记录？" @confirm="hideHistory(item.id)">
                <a-button danger size="small" ghost>移除</a-button>
              </a-popconfirm>
            </a-space>
          </div>
        </a-list-item>
      </template>
    </a-list>
  </a-drawer>

  <a-drawer v-model:open="detailOpen" title="细胞详情" width="min(440px, 96vw)">
    <a-descriptions v-if="selectedResult" :column="1" bordered size="small">
      <a-descriptions-item label="数据集">{{ selectedResult.dataset_name || selectedDataset?.name || "-" }}</a-descriptions-item>
      <a-descriptions-item label="排名">{{ selectedResult.rank }}</a-descriptions-item>
      <a-descriptions-item label="细胞编号">{{ Number(selectedResult.cell_index).toLocaleString('zh-CN') }}</a-descriptions-item>
      <a-descriptions-item label="细胞名称">{{ selectedResult.cell_name }}</a-descriptions-item>
      <a-descriptions-item label="细胞类型">{{ selectedResult.cell_type }}</a-descriptions-item>
      <a-descriptions-item label="疾病">{{ selectedResult.disease }}</a-descriptions-item>
      <a-descriptions-item label="年龄组">{{ selectedResult.age_group }}</a-descriptions-item>
      <a-descriptions-item label="距离">{{ formatDistance(selectedResult.distance) }}</a-descriptions-item>
    </a-descriptions>
    <a-alert v-if="cellDetailError" style="margin-top: 12px" type="warning" show-icon :message="cellDetailError" />
  </a-drawer>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { message } from "ant-design-vue";
import PageHeader from "@/components/PageHeader.vue";
import PlotlyPanel from "@/components/PlotlyPanel.vue";
import { api } from "@/services/api";
import { useDatasetStore } from "@/stores/datasets";
import { useQueryStore } from "@/stores/query";
import { algorithmText, formatCellIndex, formatDate, formatDistance, formatMilliseconds, metricText, statusText } from "@/utils/format";
import { readNonNegativeRouteNumber, readPositiveRouteNumber } from "@/utils/resource-actions";
import type { JointIndex, JointSearchPayload, MultiSearchPayload, SearchHistoryItem, SearchResult, SingleSearchPayload, TaskRecord } from "@/types";

const route = useRoute();
const router = useRouter();
const store = useDatasetStore();
const queryStore = useQueryStore();
const mode = ref<"single" | "multi" | "joint">("single");
const datasetId = ref<number | undefined>();
const indexId = ref<number | undefined>();
const jointIndexId = ref<number | undefined>();
const queryCellIndex = ref(0);
const topK = ref(10);
const cellType = ref<string | undefined>();
const cellTypes = ref<string[]>([]);
const targetDatasetIds = ref<number[]>([]);
const jointIndexes = ref<JointIndex[]>([]);
const queryError = ref("");
const currentTask = ref<TaskRecord | null>(null);
const detailOpen = ref(false);
const selectedResult = ref<SearchResult | null>(null);
const cellDetailError = ref("");
const historyOpen = ref(false);
const historyLoading = ref(false);
const historyItems = ref<SearchHistoryItem[]>([]);
const historyFilters = reactive({ mode: "all", source: "all", status: "all" });
const historyReady = ref(false);
const historyModeOptions = [
  { value: "all", label: "全部模式" }, { value: "single", label: "单数据集" },
  { value: "multi", label: "Fan-out" }, { value: "joint", label: "联合索引" },
];
const historySourceOptions = [
  { value: "all", label: "全部来源" }, { value: "query_lab", label: "人工检索" }, { value: "ai", label: "AI 检索" },
];
const historyStatusOptions = [
  { value: "all", label: "全部状态" }, { value: "success", label: "成功" }, { value: "error", label: "失败" },
];

const datasetOptions = computed(() => store.indexedDatasets.map((dataset) => ({ value: dataset.id, label: `${dataset.name}（${dataset.n_cells || "?"} 个细胞）` })));
const selectedDataset = computed(() => store.datasets.find((dataset) => dataset.id === datasetId.value));
const indexOptions = computed(() => (selectedDataset.value?.indexes || []).filter((idx) => idx.status === "ready").map((idx) => ({
  value: idx.id,
  label: `${algorithmText(idx.algorithm)} · ${metricText(idx.metric)} · M ${idx.M} · 查询深度 ${idx.ef_search}`,
})));
const cellTypeOptions = computed(() => cellTypes.value.map((value) => ({ value, label: value })));
const jointIndexOptions = computed(() => jointIndexes.value.filter((idx) => idx.status === "ready").map((idx) => ({ value: idx.id, label: `${idx.name}（${(idx.n_cells || 0).toLocaleString("zh-CN")} 个细胞）` })));
const selectedJointIndex = computed(() => jointIndexes.value.find((idx) => idx.id === jointIndexId.value));
const jointDatasetOptions = computed(() => (selectedJointIndex.value?.datasets || [])
  .filter((row) => row.status === "included")
  .map((row) => ({ value: row.dataset_id, label: `${row.dataset_name || row.dataset_id}（${row.n_cells || "?"} 个细胞）` })));
const activeResults = computed(() => {
  if (mode.value === "joint") return queryStore.jointResults;
  return mode.value === "single" ? queryStore.results : queryStore.multiResults;
});
const resultTableScroll = computed(() => (activeResults.value.length ? { y: 326 } : undefined));
const placeholderText = computed(() => {
  if (mode.value === "multi") return "Fan-out 跨数据集检索结果以合并表排序展示。";
  if (mode.value === "joint") return "运行联合索引检索后显示 Harmony UMAP 高亮。";
  return "运行单数据集检索后显示查询细胞和相似细胞。";
});
const resultColumns = [
  { title: "排名", key: "rank", dataIndex: "rank", width: 64, align: "right" },
  { title: "细胞", key: "cell" },
  { title: "距离", key: "distance", dataIndex: "distance", width: 104, align: "right" },
  { title: "元数据", key: "metadata", width: 148 },
  { title: "操作", key: "actions", width: 72, align: "center" },
];

async function loadJointIndexes() {
  const data = await api.jointIndexes();
  jointIndexes.value = data.joint_indexes;
}

async function onDatasetChange() {
  indexId.value = indexOptions.value[0]?.value;
  targetDatasetIds.value = store.indexedDatasets.map((dataset) => dataset.id);
  if (!datasetId.value) return;
  try {
    const data = await api.cellTypes(datasetId.value);
    cellTypes.value = data.cell_types;
  } catch {
    cellTypes.value = [];
  }
}

function onJointIndexChange() {
  datasetId.value = jointDatasetOptions.value[0]?.value;
}

function onModeChange() {
  queryStore.resetSearchState();
  currentTask.value = null;
  queryError.value = "";
  selectedResult.value = null;
  if (mode.value === "joint") {
    jointIndexId.value ||= jointIndexOptions.value[0]?.value;
    onJointIndexChange();
  } else {
    datasetId.value ||= store.indexedDatasets[0]?.id;
    void onDatasetChange();
  }
}

async function run() {
  queryError.value = "";
  currentTask.value = null;
  try {
    if (mode.value === "single") {
      if (!datasetId.value || !indexId.value) {
        message.warning("请选择数据集和索引");
        return;
      }
      await queryStore.runSearch({
        dataset_id: datasetId.value,
        index_id: indexId.value,
        query_cell_index: queryCellIndex.value,
        top_k: topK.value,
        filter_cell_type: cellType.value,
      }, (task) => {
        currentTask.value = task;
      });
    } else if (mode.value === "multi") {
      if (!datasetId.value || !indexId.value) {
        message.warning("请选择源数据集和索引");
        return;
      }
      const form = new FormData();
      form.set("dataset_id", String(datasetId.value));
      form.set("index_id", String(indexId.value));
      form.set("query_cell_index", String(queryCellIndex.value));
      form.set("top_k", String(topK.value));
      form.set("target_scope", "selected");
      targetDatasetIds.value.forEach((id) => form.append("target_dataset_ids", String(id)));
      await queryStore.runMultiSearch(form, (task) => {
        currentTask.value = task;
      });
    } else {
      if (!jointIndexId.value || !datasetId.value) {
        message.warning("请选择联合索引和查询数据集");
        return;
      }
      await queryStore.runJointSearch({
        joint_index_id: jointIndexId.value,
        query_dataset_id: datasetId.value,
        query_cell_index: queryCellIndex.value,
        top_k: topK.value,
      }, (task) => {
        currentTask.value = task;
      });
    }
  } catch (error) {
    queryError.value = (error as Error).message;
    message.error(queryError.value);
  }
}

async function openCellDetail(record: SearchResult) {
  selectedResult.value = record;
  detailOpen.value = true;
  cellDetailError.value = "";
  const detailDatasetId = record.dataset_id || datasetId.value;
  if (!detailDatasetId) return;
  try {
    const data = await api.cellMeta(detailDatasetId, record.cell_index);
    selectedResult.value = {
      ...record,
      cell_name: data.cell.cell_name || record.cell_name,
      cell_type: data.cell.cell_type || record.cell_type,
      disease: data.cell.disease || record.disease,
      age_group: data.cell.age_group || record.age_group,
    };
  } catch (error) {
    cellDetailError.value = (error as Error).message;
  }
}

function historyModeLabel(value: string) {
  return ({ single: "单数据集", multi: "Fan-out", joint: "联合索引" } as Record<string, string>)[value] || value;
}

async function loadHistory() {
  historyLoading.value = true;
  try {
    historyItems.value = (await api.searchHistory({ ...historyFilters, limit: 50 })).history;
  } catch (error) {
    message.error((error as Error).message);
  } finally {
    historyLoading.value = false;
  }
}

async function openHistoryDrawer() {
  historyOpen.value = true;
  await loadHistory();
}

async function hideHistory(id: number) {
  await api.hideSearchHistory(id);
  message.success("已从检索历史移除");
  await loadHistory();
}

async function clearHistory() {
  const data = await api.clearSearchHistory({ mode: historyFilters.mode, source: historyFilters.source });
  message.success(`已移除 ${data.hidden_count} 条历史`);
  await loadHistory();
}

function selectHistory(id: number) {
  historyOpen.value = false;
  if (Number(route.query.history_id) === id) void loadHistoryResult(id);
  else router.push({ path: "/query-lab", query: { history_id: id } });
}

function openAiConversation(conversationId: number) {
  router.push({ path: "/ai-assistant", query: { conversation_id: conversationId } });
}

async function loadHistoryResult(id: number) {
  try {
    const item = (await api.searchHistoryDetail(id)).history;
    if (!item.result) throw new Error("该历史记录没有可载入的结果。");
    queryError.value = "";
    currentTask.value = null;
    mode.value = item.mode;
    const request = item.request as Record<string, unknown>;
    queryStore.resetSearchState();
    const runId = queryStore.searchRunId;

    if (item.mode === "single") {
      datasetId.value = Number(request.dataset_id || item.dataset_id) || undefined;
      queryCellIndex.value = Number(request.query_cell_index ?? item.query_cell_index ?? 0);
      topK.value = Number(request.top_k ?? item.top_k ?? 10);
      await onDatasetChange();
      indexId.value = Number(request.index_id) || indexOptions.value[0]?.value;
      cellType.value = typeof request.filter_cell_type === "string" ? request.filter_cell_type : undefined;
      queryStore.applySingleSearchPayload(item.result as SingleSearchPayload);
      if (!queryStore.scatter && queryStore.results.length && datasetId.value) {
        void queryStore.runSearchPlot({
          dataset_id: datasetId.value,
          query_cell_index: queryCellIndex.value,
          result_cell_indices: queryStore.results.map((row) => row.cell_index),
        }, runId);
      }
    } else if (item.mode === "multi") {
      datasetId.value = Number(request.dataset_id || item.dataset_id) || undefined;
      queryCellIndex.value = Number(request.query_cell_index ?? item.query_cell_index ?? 0);
      topK.value = Number(request.top_k ?? item.top_k ?? 20);
      await onDatasetChange();
      indexId.value = Number(request.index_id) || indexOptions.value[0]?.value;
      targetDatasetIds.value = Array.isArray(request.target_dataset_ids)
        ? request.target_dataset_ids.map(Number) : [];
      queryStore.applyMultiSearchPayload(item.result as MultiSearchPayload);
    } else {
      jointIndexId.value = Number(request.joint_index_id) || undefined;
      queryCellIndex.value = Number(request.query_cell_index ?? item.query_cell_index ?? 0);
      topK.value = Number(request.top_k ?? item.top_k ?? 20);
      datasetId.value = Number(request.query_dataset_id || item.dataset_id) || undefined;
      queryStore.applyJointSearchPayload(item.result as JointSearchPayload);
      const labels = queryStore.jointResults.map((row) => row.global_label).filter((value): value is number => typeof value === "number");
      if (queryStore.jointMeta && labels.length) {
        void queryStore.runJointSearchPlot({
          joint_index_id: queryStore.jointMeta.joint_index_id,
          query_global_label: queryStore.jointMeta.query_global_label,
          result_global_labels: labels,
        }, runId);
      }
    }
    if (item.legacy) message.warning("已载入旧结果；重新运行前请确认索引参数。");
    else message.success("历史结果已载入，ANN 未重复执行。");
  } catch (error) {
    queryError.value = (error as Error).message;
    message.error(queryError.value);
  }
}

onMounted(async () => {
  await store.loadAll();
  await loadJointIndexes();
  if (["single", "multi", "joint"].includes(String(route.query.mode))) {
    mode.value = String(route.query.mode) as "single" | "multi" | "joint";
  }
  datasetId.value = readPositiveRouteNumber(route.query.dataset) || store.indexedDatasets[0]?.id;
  queryCellIndex.value = readNonNegativeRouteNumber(route.query.cell_index) ?? 0;
  topK.value = readPositiveRouteNumber(route.query.top_k) || 10;
  await onDatasetChange();
  indexId.value = readPositiveRouteNumber(route.query.index_id) || indexOptions.value[0]?.value;
  if (typeof route.query.filter_cell_type === "string" && route.query.filter_cell_type) {
    cellType.value = route.query.filter_cell_type;
  }
  jointIndexId.value = jointIndexOptions.value[0]?.value;
  historyReady.value = true;
  const historyId = readPositiveRouteNumber(route.query.history_id);
  if (historyId) await loadHistoryResult(historyId);
});

watch(() => route.query.history_id, (value) => {
  const id = readPositiveRouteNumber(value);
  if (historyReady.value && id) void loadHistoryResult(id);
});
</script>

<style scoped>
.query-workbench {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}

.query-panel {
  position: sticky;
  top: 76px;
}

.panel-help {
  margin: -4px 0 16px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.55;
}

.field-help {
  margin-top: 5px;
  color: #94a3b8;
  font-size: 12px;
}

.dataset-check-list {
  width: 100%;
  max-height: 160px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 10px;
  border: 1px solid #dfe5ed;
  border-radius: 8px;
}

.result-table {
  margin-top: 0;
}

.rank-cell,
.numeric-cell {
  font-variant-numeric: tabular-nums;
}

.rank-cell {
  color: #64748b;
}

.cell-primary {
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #172033;
  font-weight: 600;
}

.cell-secondary {
  margin-top: 4px;
  display: flex;
  align-items: center;
  gap: 7px;
  color: #64748b;
  font-size: 12px;
  flex-wrap: wrap;
}

.cell-secondary span + span::before {
  content: "·";
  margin-right: 7px;
  color: #cbd5e1;
}

.metadata-cell {
  display: flex;
  flex-direction: column;
  gap: 3px;
  color: #475569;
  font-size: 12px;
}

.plot-surface {
  min-width: 0;
}

.plot-surface .placeholder-panel {
  margin: 14px;
}

.history-filters {
  margin-bottom: 14px;
}

.history-record { width: 100%; }
.history-title { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 6px; }
.history-meta { margin-bottom: 9px; color: #64748b; font-size: 13px; }

@media (max-width: 1240px) {
  .query-workbench {
    grid-template-columns: 300px minmax(0, 1fr);
  }
}
</style>
