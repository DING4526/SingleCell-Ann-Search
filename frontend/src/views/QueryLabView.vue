<template>
  <PageHeader title="Query Lab" description="执行单数据集相似细胞检索或跨数据集 fan-out 合并检索，并查看结果表与嵌入空间高亮。">
    <template #actions>
      <a-segmented v-model:value="mode" :options="[{ label: 'Single Dataset', value: 'single' }, { label: 'Cross Dataset', value: 'multi' }]" />
    </template>
  </PageHeader>

  <div class="split-workbench">
    <div class="surface surface-pad">
      <div class="panel-title">Query Context</div>
      <a-form layout="vertical" @finish="run">
        <a-form-item label="Dataset">
          <a-select v-model:value="datasetId" :options="datasetOptions" placeholder="选择数据集" @change="onDatasetChange" />
        </a-form-item>
        <a-form-item label="Index">
          <a-select v-model:value="indexId" :options="indexOptions" placeholder="选择 ready 索引" />
        </a-form-item>
        <a-form-item label="Query Cell Index">
          <a-input-number v-model:value="queryCellIndex" :min="0" :max="selectedDataset?.n_cells ? selectedDataset.n_cells - 1 : undefined" style="width: 100%" />
          <div class="muted" style="font-size:12px;margin-top:4px">范围 0 ~ {{ selectedDataset?.n_cells ? selectedDataset.n_cells - 1 : "?" }}</div>
        </a-form-item>
        <a-form-item label="Top-K">
          <a-input-number v-model:value="topK" :min="1" :max="100" style="width: 100%" />
        </a-form-item>
        <a-form-item v-if="mode === 'single'" label="Cell Type Filter">
          <a-select v-model:value="cellType" allow-clear placeholder="全部细胞类型" :options="cellTypeOptions" />
        </a-form-item>
        <a-form-item v-if="mode === 'multi'" label="Target Datasets">
          <a-checkbox-group v-model:value="targetDatasetIds" style="display:flex;flex-direction:column;gap:6px">
            <a-checkbox v-for="dataset in store.indexedDatasets" :key="dataset.id" :value="dataset.id">{{ dataset.name }}</a-checkbox>
          </a-checkbox-group>
        </a-form-item>
        <a-button type="primary" html-type="submit" block :loading="queryStore.loading">Run Query</a-button>
      </a-form>
    </div>

    <div class="stack">
      <div class="surface">
        <div class="toolbar">
          <span class="toolbar-title">Results</span>
          <a-space>
            <a-tag v-if="queryStore.queryTimeMs !== null">Time {{ queryStore.queryTimeMs }} ms</a-tag>
            <a-tag>{{ activeResults.length }} cells</a-tag>
          </a-space>
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
          </template>
        </a-table>
      </div>

      <div class="surface">
        <div class="toolbar"><span class="toolbar-title">Embedding Highlight</span></div>
        <div class="surface-pad">
          <PlotlyPanel v-if="queryStore.scatter && mode === 'single'" :payload="queryStore.scatter" />
          <div v-else class="placeholder-panel">
            {{ mode === 'multi' ? '跨数据集检索结果以合并表排序展示；后续可接入跨数据集嵌入对齐图。' : '运行单数据集检索后显示查询细胞和相似细胞。' }}
          </div>
        </div>
      </div>
    </div>
  </div>
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

const datasetOptions = computed(() => store.indexedDatasets.map((dataset) => ({ value: dataset.id, label: `${dataset.name} (${dataset.n_cells || "?"} cells)` })));
const selectedDataset = computed(() => store.datasets.find((dataset) => dataset.id === datasetId.value));
const indexOptions = computed(() => (selectedDataset.value?.indexes || []).filter((idx) => idx.status === "ready").map((idx) => ({ value: idx.id, label: `${idx.algorithm} · ${idx.metric.toUpperCase()} · M=${idx.M} · ef=${idx.ef_search}` })));
const cellTypeOptions = computed(() => cellTypes.value.map((value) => ({ value, label: value })));
const activeResults = computed(() => (mode.value === "single" ? queryStore.results : queryStore.multiResults));
const resultColumns = [
  { title: "#", dataIndex: "rank", width: 58 },
  { title: "Dataset", key: "dataset", width: 180 },
  { title: "Cell", key: "cell", width: 260 },
  { title: "Distance", dataIndex: "distance", width: 120 },
  { title: "Disease", dataIndex: "disease", width: 120 },
  { title: "Age", dataIndex: "age_group", width: 120 },
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
    message.error((error as Error).message);
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
