<template>
  <PageHeader title="检索实验室" description="执行单数据集相似细胞检索或跨数据集 fan-out 合并检索，并查看结果表与嵌入空间高亮。">
    <template #actions>
      <a-segmented v-model:value="mode" :options="[{ label: '单数据集', value: 'single' }, { label: '跨数据集', value: 'multi' }]" />
    </template>
  </PageHeader>

  <div class="split-workbench">
    <div class="surface surface-pad">
      <div class="panel-title">检索上下文</div>
      <a-form layout="vertical">
        <a-form-item label="数据集">
          <a-select v-model:value="datasetId" :options="datasetOptions" placeholder="选择数据集" @change="onDatasetChange" />
        </a-form-item>
        <a-form-item label="索引">
          <a-select v-model:value="indexId" :options="indexOptions" placeholder="选择可用索引" />
        </a-form-item>
        <a-form-item label="查询细胞编号">
          <a-input-number v-model:value="queryCellIndex" :min="0" :max="selectedDataset?.n_cells ? selectedDataset.n_cells - 1 : undefined" style="width: 100%" />
          <div class="muted" style="font-size:12px;margin-top:4px">范围 0 ~ {{ selectedDataset?.n_cells ? selectedDataset.n_cells - 1 : "?" }}</div>
        </a-form-item>
        <a-form-item label="Top-K">
          <a-input-number v-model:value="topK" :min="1" :max="100" style="width: 100%" />
        </a-form-item>
        <a-form-item v-if="mode === 'single'" label="细胞类型过滤">
          <a-select v-model:value="cellType" allow-clear placeholder="全部细胞类型" :options="cellTypeOptions" />
        </a-form-item>
        <a-form-item v-if="mode === 'multi'" label="目标数据集">
          <a-checkbox-group v-model:value="targetDatasetIds" style="display:flex;flex-direction:column;gap:6px">
            <a-checkbox v-for="dataset in store.indexedDatasets" :key="dataset.id" :value="dataset.id">{{ dataset.name }}</a-checkbox>
          </a-checkbox-group>
        </a-form-item>
        <a-button type="primary" block :loading="queryStore.loading" @click="run">运行检索</a-button>
      </a-form>
    </div>

    <div class="stack">
      <div class="surface">
        <div class="toolbar">
          <span class="toolbar-title">检索结果</span>
          <a-space>
            <a-tag v-if="queryStore.queryTimeMs !== null">耗时 {{ queryStore.queryTimeMs }} ms</a-tag>
            <a-tag v-if="mode === 'multi' && queryStore.multiMeta">检索 {{ queryStore.multiMeta.searched_dataset_count }} 个数据集</a-tag>
            <a-tag>{{ activeResults.length }} 个细胞</a-tag>
          </a-space>
        </div>
        <div v-if="queryError" class="surface-pad" style="padding-bottom:0">
          <a-alert type="error" show-icon :message="queryError" />
        </div>
        <a-table class="result-table" :data-source="activeResults" :columns="resultColumns" row-key="rank" size="small" :scroll="{ x: 900, y: 320 }" :pagination="false">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'cell'">
              <a-space direction="vertical" size="small">
                <span>#{{ record.cell_index }} · {{ record.cell_name }}</span>
                <span class="muted">{{ record.cell_type }}</span>
              </a-space>
            </template>
            <template v-if="column.key === 'dataset'">
              {{ record.dataset_name || selectedDataset?.name || "-" }}
            </template>
            <template v-if="column.key === 'actions'">
              <a-button size="small" @click="openCellDetail(record)">详情</a-button>
            </template>
          </template>
        </a-table>
      </div>

      <div class="surface">
        <div class="toolbar"><span class="toolbar-title">嵌入空间高亮</span></div>
        <div class="surface-pad">
          <PlotlyPanel v-if="queryStore.scatter && mode === 'single'" :payload="queryStore.scatter" />
          <div v-else class="placeholder-panel">
            {{ mode === 'multi' ? '跨数据集检索结果以合并表排序展示；后续可接入跨数据集嵌入对齐图。' : '运行单数据集检索后显示查询细胞和相似细胞。' }}
          </div>
        </div>
      </div>
    </div>
  </div>

  <a-drawer v-model:open="detailOpen" title="细胞详情" width="420">
    <a-descriptions v-if="selectedResult" :column="1" bordered size="small">
      <a-descriptions-item label="数据集">{{ selectedResult.dataset_name || selectedDataset?.name || "-" }}</a-descriptions-item>
      <a-descriptions-item label="Rank">{{ selectedResult.rank }}</a-descriptions-item>
      <a-descriptions-item label="细胞编号">{{ selectedResult.cell_index }}</a-descriptions-item>
      <a-descriptions-item label="细胞名称">{{ selectedResult.cell_name }}</a-descriptions-item>
      <a-descriptions-item label="细胞类型">{{ selectedResult.cell_type }}</a-descriptions-item>
      <a-descriptions-item label="疾病">{{ selectedResult.disease }}</a-descriptions-item>
      <a-descriptions-item label="年龄组">{{ selectedResult.age_group }}</a-descriptions-item>
      <a-descriptions-item label="距离">{{ selectedResult.distance }}</a-descriptions-item>
    </a-descriptions>
    <a-alert v-if="cellDetailError" style="margin-top: 12px" type="warning" show-icon :message="cellDetailError" />
  </a-drawer>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { message } from "ant-design-vue";
import PageHeader from "@/components/PageHeader.vue";
import PlotlyPanel from "@/components/PlotlyPanel.vue";
import { api } from "@/services/api";
import { useDatasetStore } from "@/stores/datasets";
import { useQueryStore } from "@/stores/query";
import type { SearchResult } from "@/types";

const route = useRoute();
const store = useDatasetStore();
const queryStore = useQueryStore();
const mode = ref<"single" | "multi">("single");
const datasetId = ref<number | undefined>();
const indexId = ref<number | undefined>();
const queryCellIndex = ref(0);
const topK = ref(10);
const cellType = ref<string | undefined>();
const cellTypes = ref<string[]>([]);
const targetDatasetIds = ref<number[]>([]);
const queryError = ref("");
const detailOpen = ref(false);
const selectedResult = ref<SearchResult | null>(null);
const cellDetailError = ref("");

const datasetOptions = computed(() => store.indexedDatasets.map((dataset) => ({ value: dataset.id, label: `${dataset.name}（${dataset.n_cells || "?"} 个细胞）` })));
const selectedDataset = computed(() => store.datasets.find((dataset) => dataset.id === datasetId.value));
const indexOptions = computed(() => (selectedDataset.value?.indexes || []).filter((idx) => idx.status === "ready").map((idx) => ({ value: idx.id, label: `${idx.algorithm} · ${idx.metric.toUpperCase()} · M=${idx.M} · ef=${idx.ef_search}` })));
const cellTypeOptions = computed(() => cellTypes.value.map((value) => ({ value, label: value })));
const activeResults = computed(() => (mode.value === "single" ? queryStore.results : queryStore.multiResults));
const resultColumns = [
  { title: "#", dataIndex: "rank", width: 58 },
  { title: "数据集", key: "dataset", width: 180 },
  { title: "细胞", key: "cell", width: 260 },
  { title: "距离", dataIndex: "distance", width: 120 },
  { title: "疾病", dataIndex: "disease", width: 120 },
  { title: "年龄组", dataIndex: "age_group", width: 120 },
  { title: "操作", key: "actions", fixed: "right", width: 90 },
];

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

async function run() {
  if (!datasetId.value || !indexId.value) {
    message.warning("请选择数据集和索引");
    return;
  }
  queryError.value = "";
  try {
    if (mode.value === "single") {
      await queryStore.runSearch({
        dataset_id: datasetId.value,
        index_id: indexId.value,
        query_cell_index: queryCellIndex.value,
        top_k: topK.value,
        filter_cell_type: cellType.value,
      });
    } else {
      const form = new FormData();
      form.set("dataset_id", String(datasetId.value));
      form.set("index_id", String(indexId.value));
      form.set("query_cell_index", String(queryCellIndex.value));
      form.set("top_k", String(topK.value));
      form.set("target_scope", "selected");
      targetDatasetIds.value.forEach((id) => form.append("target_dataset_ids", String(id)));
      await queryStore.runMultiSearch(form);
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

onMounted(async () => {
  await store.loadAll();
  datasetId.value = Number(route.query.dataset) || store.indexedDatasets[0]?.id;
  queryCellIndex.value = Number(route.query.cell_index) || 0;
  await onDatasetChange();
  indexId.value = Number(route.query.index_id) || indexOptions.value[0]?.value;
});
</script>
