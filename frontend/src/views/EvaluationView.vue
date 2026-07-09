<template>
  <PageHeader title="Evaluation" description="对比 ANN 与精确检索，记录 Recall@K、响应时间和加速比。">
    <template #actions>
      <a-button type="primary" :loading="queryStore.loading" @click="runEvaluation">Run Evaluation</a-button>
    </template>
  </PageHeader>

  <div class="split-workbench">
    <div class="surface surface-pad">
      <div class="panel-title">Evaluation Setup</div>
      <a-form layout="vertical">
        <a-form-item label="Dataset">
          <a-select v-model:value="datasetId" :options="datasetOptions" @change="onDatasetChange" />
        </a-form-item>
        <a-form-item label="Index">
          <a-select v-model:value="indexId" :options="indexOptions" />
        </a-form-item>
        <a-form-item label="Sample Size">
          <a-input-number v-model:value="sampleSize" :min="1" :max="50" style="width:100%" />
        </a-form-item>
        <a-form-item label="Top-K">
          <a-input-number v-model:value="topK" :min="1" :max="100" style="width:100%" />
        </a-form-item>
      </a-form>
    </div>

    <div class="stack">
      <div class="metric-grid" v-if="queryStore.metrics">
        <div class="metric-tile"><div class="metric-label">Recall@{{ queryStore.metrics.top_k }}</div><div class="metric-value">{{ (queryStore.metrics.avg_recall_at_k * 100).toFixed(1) }}%</div></div>
        <div class="metric-tile"><div class="metric-label">Speedup</div><div class="metric-value">{{ queryStore.metrics.speedup }}x</div></div>
        <div class="metric-tile"><div class="metric-label">ANN ms</div><div class="metric-value">{{ queryStore.metrics.avg_ann_time_ms }}</div></div>
        <div class="metric-tile"><div class="metric-label">Exact ms</div><div class="metric-value">{{ queryStore.metrics.avg_exact_time_ms }}</div></div>
      </div>
      <div class="surface">
        <div class="toolbar"><span class="toolbar-title">Performance Chart</span></div>
        <div class="surface-pad">
          <PlotlyPanel v-if="queryStore.evaluationPlot" :payload="queryStore.evaluationPlot" />
          <div v-else class="placeholder-panel">运行评估后展示性能图表。</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { message } from "ant-design-vue";
import PageHeader from "@/components/PageHeader.vue";
import PlotlyPanel from "@/components/PlotlyPanel.vue";
import { useDatasetStore } from "@/stores/datasets";
import { useQueryStore } from "@/stores/query";

const store = useDatasetStore();
const queryStore = useQueryStore();
const datasetId = ref<number | undefined>();
const indexId = ref<number | undefined>();
const sampleSize = ref(10);
const topK = ref(10);
const datasetOptions = computed(() => store.indexedDatasets.map((dataset) => ({ value: dataset.id, label: dataset.name })));
const selectedDataset = computed(() => store.datasets.find((dataset) => dataset.id === datasetId.value));
const indexOptions = computed(() => (selectedDataset.value?.indexes || []).filter((idx) => idx.status === "ready").map((idx) => ({ value: idx.id, label: `${idx.algorithm} · ${idx.metric.toUpperCase()} · M=${idx.M}` })));

function onDatasetChange() {
  indexId.value = indexOptions.value[0]?.value;
}

async function runEvaluation() {
  if (!datasetId.value || !indexId.value) {
    message.warning("请选择数据集和索引");
    return;
  }
  try {
    await queryStore.evaluate({ dataset_id: datasetId.value, index_id: indexId.value, sample_size: sampleSize.value, eval_top_k: topK.value });
  } catch (error) {
    message.error((error as Error).message);
  }
}

onMounted(async () => {
  await store.loadAll();
  datasetId.value = store.indexedDatasets[0]?.id;
  onDatasetChange();
});
</script>
