<template>
  <PageHeader title="索引实验室" description="一次完成候选构建、统一真实评估和最终索引选优。">
    <template #actions>
      <a-space class="page-actions" wrap>
        <a-select v-model:value="selectedDatasetId" class="dataset-picker" placeholder="选择数据集" :options="datasetOptions" @change="onDatasetChange" />
        <a-button @click="historyOpen = true">历史实验</a-button>
      </a-space>
    </template>
  </PageHeader>

  <section class="surface retained-strip">
    <div class="retained-copy">
      <span class="eyebrow">当前保留集</span>
      <strong>{{ dataset?.name || "未选择数据集" }}</strong>
      <span>{{ activeIndexes.length ? `${activeIndexes.length} 个 active 索引可用于检索` : "尚无可检索索引" }}</span>
    </div>
    <div class="retained-list">
      <div v-for="index in activeIndexes" :key="index.id" class="retained-chip">
        <span>#{{ index.id }} {{ algorithmShort(index.algorithm) }}</span>
        <small>{{ selectionText(index.selection_labels) }}</small>
      </div>
      <a-button v-if="activeIndexes.length" type="link" @click="goToQuery">进入检索实验室</a-button>
    </div>
  </section>

  <section class="surface config-panel">
    <div class="section-head">
      <div>
        <span class="step-label">01</span>
        <div>
          <h2>配置一次完整实验</h2>
          <p>六个代表性 ANN 候选将在完整数据集上构建，并共享同一个 FAISS Flat 精确基线。</p>
        </div>
      </div>
      <a-tag color="blue">FAISS Flat · 精确参考</a-tag>
    </div>

    <div class="config-grid">
      <div class="config-field">
        <span>距离度量</span>
        <a-segmented v-model:value="form.metric" :options="metricOptions" />
      </div>
      <div class="config-field">
        <span>Top-K</span>
        <a-input-number v-model:value="form.top_k" :min="1" :max="100" />
      </div>
      <div class="config-summary">
        <span>评估强度</span>
        <strong>{{ form.sample_size }} 个查询 × {{ form.repetitions }} 轮</strong>
        <small>预热 {{ form.warmup_count }} 次 · seed {{ form.seed }}</small>
      </div>
      <div class="config-summary">
        <span>候选预设</span>
        <strong>平衡对比 · {{ candidates.length }} 个</strong>
        <small>HNSW / RP-HNSW / IVF / PQ</small>
      </div>
      <div class="config-actions">
        <a-button @click="advancedOpen = true">高级配置</a-button>
        <a-button type="primary" :loading="experimentRunning" :disabled="!canStartExperiment" @click="startExperiment">开始构建与评估</a-button>
      </div>
    </div>
    <a-alert v-if="blockingExperiment" class="config-alert" type="warning" show-icon :message="`实验 #${blockingExperiment.id} 尚待处理，请先完成选优或放弃。`" />
  </section>

  <section v-if="experimentResult && ['pending', 'running'].includes(experimentResult.status)" class="surface progress-panel">
    <div class="section-head compact-head">
      <div>
        <span class="step-label">02</span>
        <div><h2>构建与真实评估</h2><p>{{ currentTask?.message || "候选任务运行中，离开页面也不会中断。" }}</p></div>
      </div>
      <a-tag color="processing">实验 #{{ experimentResult.id }}</a-tag>
    </div>
    <a-progress :percent="currentTask?.progress || progressFromRuns" status="active" />
    <div class="run-status-grid">
      <div v-for="run in experimentResult.runs || []" :key="run.id" class="run-status-card">
        <StatusTag :status="run.status" />
        <strong>{{ run.name }}</strong>
        <small>{{ run.error_message || paramsSummary(run.params) }}</small>
      </div>
    </div>
  </section>

  <section v-if="experimentResult && !['pending', 'running'].includes(experimentResult.status)" class="result-stack">
    <div class="surface result-panel">
      <div class="section-head compact-head">
        <div>
          <span class="step-label">02</span>
          <div>
            <h2>统一比较结果</h2>
            <p>所有成功候选均使用同一批查询、相同预热和重复次数。</p>
          </div>
        </div>
        <a-space wrap>
          <a-tag>实验 #{{ experimentResult.id }}</a-tag>
          <StatusTag :status="experimentResult.status" />
          <a-button v-if="canDiscard" danger size="small" @click="confirmDiscard">放弃实验</a-button>
        </a-space>
      </div>

      <div class="baseline-bar">
        <div><span>精确基线</span><strong>FAISS Flat</strong></div>
        <div><span>平均耗时</span><strong>{{ fixed(experimentResult.exact_baseline.avg_query_time_ms) }} ms</strong></div>
        <div><span>P95</span><strong>{{ fixed(experimentResult.exact_baseline.p95_query_time_ms) }} ms</strong></div>
        <div><span>成功候选</span><strong>{{ successfulRuns.length }} / {{ experimentResult.candidate_count }}</strong></div>
      </div>

      <div class="comparison-layout">
        <div class="chart-card">
          <div class="card-title">Recall–P95 分布</div>
          <PlotlyPanel :payload="comparisonPlot" :height="360" />
        </div>
        <aside class="shortlist-card">
          <div class="card-title">最终保留候选</div>
          <p>系统已按质量、综合表现和速度预选，可调整为 2–3 个。</p>
          <div v-if="selectedRuns.length" class="shortlist-items">
            <div v-for="run in selectedRuns" :key="run.id" class="shortlist-item">
              <div><strong>{{ run.name }}</strong><small>{{ percent(run.recall_at_k) }} · {{ fixed(run.speedup) }}x</small></div>
              <div class="tag-row"><a-tag v-for="tag in recommendationTags(run.recommendation)" :key="tag" :color="recommendationColor(tag)">{{ recommendationText(tag) }}</a-tag></div>
            </div>
          </div>
          <a-empty v-else :image="simpleImage" description="选择 2–3 个候选" />
          <a-alert v-if="hasLowRecallSelection" type="warning" show-icon message="选择中包含 Recall 低于 90% 的研究候选。" />
        </aside>
      </div>

      <a-table class="comparison-table" :data-source="experimentResult.runs || []" :columns="columns" row-key="id" size="small" :pagination="false" :scroll="{ x: 980 }">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'candidate'">
            <div class="candidate-cell"><strong>{{ record.name }}</strong><small>{{ algorithmShort(record.algorithm) }}</small></div>
          </template>
          <template v-else-if="column.key === 'status'"><StatusTag :status="record.status" /></template>
          <template v-else-if="column.key === 'recall'">{{ percent(record.recall_at_k) }}</template>
          <template v-else-if="column.key === 'query'">{{ fixed(record.avg_query_time_ms) }} / {{ fixed(record.p95_query_time_ms) }}</template>
          <template v-else-if="column.key === 'speedup'">{{ fixed(record.speedup) }}x</template>
          <template v-else-if="column.key === 'build'">{{ fixed(record.build_time_ms) }} ms<br><small>{{ formatBytes(record.index_size_bytes) }}</small></template>
          <template v-else-if="column.key === 'recommendation'">
            <a-space :size="4" wrap><a-tag v-for="tag in recommendationTags(record.recommendation)" :key="tag" :color="recommendationColor(tag)">{{ recommendationText(tag) }}</a-tag></a-space>
          </template>
          <template v-else-if="column.key === 'select'">
            <a-checkbox :checked="selectedRunIds.includes(record.id)" :disabled="selectionDisabled(record)" @change="onRunSelectionChange(record, $event)">保留</a-checkbox>
          </template>
        </template>
        <template #expandedRowRender="{ record }">
          <div class="expanded-detail">
            <span><strong>参数：</strong>{{ paramsSummary(record.params) }}</span>
            <span v-if="record.error_message"><strong>失败原因：</strong>{{ record.error_message }}</span>
            <span v-if="record.skip_reason"><strong>跳过原因：</strong>{{ record.skip_reason }}</span>
          </div>
        </template>
      </a-table>
    </div>

    <div v-if="experimentResult.status === 'ready_for_selection'" class="surface finalize-bar">
      <div>
        <span class="step-label">03</span>
        <div><strong>完成选优</strong><small>保留 {{ selectedRunIds.length }} 个 · 预计释放 {{ formatBytes(estimatedReclaimBytes) }}</small></div>
      </div>
      <a-button type="primary" size="large" :disabled="selectedRunIds.length < 2 || selectedRunIds.length > 3" @click="finalizeOpen = true">确认保留并清理其它索引</a-button>
    </div>

    <div v-if="experimentResult.status === 'finalized'" class="surface completed-panel">
      <div><span class="step-label done">✓</span><div><strong>选优已完成</strong><small>已保留 {{ experimentResult.selected_run_ids.length }} 个索引，释放 {{ formatBytes(experimentResult.reclaimed_bytes) }}</small></div></div>
      <a-space>
        <a-button v-if="cleanupErrors.length" danger @click="retryCleanup">重试失败清理</a-button>
        <a-button type="primary" @click="goToQuery">进入检索实验室</a-button>
      </a-space>
    </div>
  </section>

  <a-drawer v-model:open="advancedOpen" title="高级实验配置" width="620">
    <a-alert message="FAISS Flat 精确基线固定启用；这里只配置可被最终保留的 ANN 候选。" type="info" show-icon />
    <div class="advanced-fields">
      <a-form layout="vertical">
        <div class="advanced-grid">
          <a-form-item label="查询样本"><a-input-number v-model:value="form.sample_size" :min="1" :max="200" /></a-form-item>
          <a-form-item label="重复轮数"><a-input-number v-model:value="form.repetitions" :min="1" :max="10" /></a-form-item>
          <a-form-item label="预热查询"><a-input-number v-model:value="form.warmup_count" :min="0" :max="200" /></a-form-item>
          <a-form-item label="随机种子"><a-input-number v-model:value="form.seed" :min="0" :max="2147483647" /></a-form-item>
        </div>
      </a-form>
      <div class="candidate-editor-head"><strong>候选配置（{{ candidates.length }}/12）</strong><a-space><a-button size="small" @click="resetCandidates">恢复预设</a-button><a-button size="small" :disabled="candidates.length >= 12" @click="addCandidate">添加候选</a-button></a-space></div>
      <article v-for="candidate in candidates" :key="candidate.key" class="candidate-editor-card">
        <div class="candidate-editor-row">
          <a-input v-model:value="candidate.name" placeholder="候选名称" />
          <a-select v-model:value="candidate.algorithm" :options="candidateAlgorithmOptions" @change="() => changeCandidateAlgorithm(candidate)" />
          <a-button size="small" @click="duplicateCandidate(candidate)">复制</a-button>
          <a-button size="small" danger :disabled="candidates.length <= 2" @click="removeCandidate(candidate.key)">删除</a-button>
        </div>
        <a-textarea v-model:value="candidate.paramsText" :rows="3" placeholder="JSON 参数" />
      </article>
    </div>
  </a-drawer>

  <a-drawer v-model:open="historyOpen" title="实验历史" width="520">
    <a-list :data-source="experiments" :loading="historyLoading">
      <template #renderItem="{ item }">
        <a-list-item>
          <a-list-item-meta :title="`实验 #${item.id} · ${item.dataset_name || '-'}`" :description="`${item.metric.toUpperCase()} · Top-${item.top_k} · ${item.candidate_count} 个候选 · ${formatDate(item.created_at)}`">
            <template #avatar><StatusTag :status="item.status" /></template>
          </a-list-item-meta>
          <a-button size="small" @click="openHistoryExperiment(item.id)">载入</a-button>
        </a-list-item>
      </template>
    </a-list>
  </a-drawer>

  <a-modal v-model:open="finalizeOpen" title="确认最终保留集合" ok-text="确认保留并立即清理" cancel-text="返回调整" :confirm-loading="finalizing" @ok="finalizeSelection">
    <a-alert type="warning" show-icon message="确认后，新选择将成为该数据集唯一可检索索引；物理文件删除不可撤销。" />
    <div class="confirm-group"><strong>即将保留</strong><ul><li v-for="run in selectedRuns" :key="run.id">{{ run.name }} · Recall {{ percent(run.recall_at_k) }} · {{ fixed(run.speedup) }}x</li></ul></div>
    <div class="confirm-group"><strong>即将退役的旧 active 索引</strong><ul><li v-for="index in activeIndexes" :key="index.id">#{{ index.id }} {{ algorithmShort(index.algorithm) }}</li><li v-if="!activeIndexes.length">无</li></ul></div>
    <div class="confirm-group"><strong>即将清理的未选候选</strong><ul><li v-for="run in candidatesToClean" :key="run.id">{{ run.name }} · {{ formatBytes(run.index_size_bytes) }}</li><li v-if="!candidatesToClean.length">无</li></ul></div>
    <div class="reclaim-total">预计释放 <strong>{{ formatBytes(estimatedReclaimBytes) }}</strong></div>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { Empty, Modal, message } from "ant-design-vue";
import { useRoute, useRouter } from "vue-router";
import PageHeader from "@/components/PageHeader.vue";
import PlotlyPanel from "@/components/PlotlyPanel.vue";
import StatusTag from "@/components/StatusTag.vue";
import { api } from "@/services/api";
import { useDatasetStore } from "@/stores/datasets";
import { useTaskStore } from "@/stores/tasks";
import { formatDate, recommendationColor, recommendationText, statusText } from "@/utils/format";
import type { AnnAlgorithm, AnnIndex, IndexCandidateConfig, IndexExperiment, IndexExperimentRun, PlotlyPayload, TaskRecord } from "@/types";

type CandidateDraft = IndexCandidateConfig & { paramsText: string };

const route = useRoute();
const router = useRouter();
const store = useDatasetStore();
const taskStore = useTaskStore();
const simpleImage = Empty.PRESENTED_IMAGE_SIMPLE;
const selectedDatasetId = ref<number | undefined>();
const algorithms = ref<AnnAlgorithm[]>([]);
const experiments = ref<IndexExperiment[]>([]);
const experimentResult = ref<IndexExperiment | null>(null);
const selectedRunIds = ref<number[]>([]);
const candidates = ref<CandidateDraft[]>([]);
const currentTask = ref<TaskRecord | null>(null);
const experimentRunning = ref(false);
const finalizing = ref(false);
const advancedOpen = ref(false);
const historyOpen = ref(false);
const historyLoading = ref(false);
const finalizeOpen = ref(false);
let pollingTimer: number | undefined;
let selectionExperimentId: number | undefined;

const form = reactive({ metric: "l2", top_k: 10, sample_size: 100, seed: 42, repetitions: 3, warmup_count: 10 });
const metricOptions = [{ label: "L2", value: "l2" }, { label: "Cosine", value: "cosine" }];
const columns = [
  { title: "候选", key: "candidate", width: 180 },
  { title: "状态", key: "status", width: 90 },
  { title: "Recall", key: "recall", width: 90 },
  { title: "平均 / P95 ms", key: "query", width: 135 },
  { title: "加速比", key: "speedup", width: 90 },
  { title: "构建 / 体积", key: "build", width: 120 },
  { title: "推荐", key: "recommendation", width: 190 },
  { title: "选择", key: "select", width: 100 },
];

const dataset = computed(() => store.current);
const datasetOptions = computed(() => store.datasets.map((item) => ({ value: item.id, label: `${item.name}（${statusText(item.status)}）` })));
const activeIndexes = computed(() => (dataset.value?.indexes || []).filter((index) => index.status === "ready" && index.lifecycle === "active"));
const candidateAlgorithmOptions = computed(() => algorithms.value.filter((item) => item.available && item.key !== "faiss_flat").map((item) => ({ value: item.key, label: item.label })));
const blockingExperiment = computed(() => experiments.value.find((item) => ["pending", "running", "ready_for_selection"].includes(item.status)) || null);
const canStartExperiment = computed(() => Boolean(dataset.value?.can_manage && ["processed", "indexed"].includes(dataset.value.status) && !blockingExperiment.value));
const successfulRuns = computed(() => (experimentResult.value?.runs || []).filter((run) => run.status === "success"));
const selectedRuns = computed(() => selectedRunIds.value.map((id) => successfulRuns.value.find((run) => run.id === id)).filter((run): run is IndexExperimentRun => Boolean(run)));
const candidatesToClean = computed(() => successfulRuns.value.filter((run) => !selectedRunIds.value.includes(run.id)));
const hasLowRecallSelection = computed(() => selectedRuns.value.some((run) => (run.recall_at_k || 0) < 0.90));
const cleanupErrors = computed(() => experimentResult.value?.finalization?.cleanup_errors || []);
const canDiscard = computed(() => Boolean(experimentResult.value && experimentResult.value.workflow_version >= 2 && !["running", "finalized", "discarded"].includes(experimentResult.value.status)));
const progressFromRuns = computed(() => {
  const runs = experimentResult.value?.runs || [];
  if (!runs.length) return 5;
  const scores: Record<string, number> = { pending: 0, building: 35, evaluating: 75, success: 100, error: 100, skipped: 100 };
  return Math.round(runs.reduce((sum, run) => sum + (scores[run.status] || 0), 0) / runs.length);
});
const estimatedReclaimBytes = computed(() => {
  const activeBytes = activeIndexes.value.reduce((sum, index) => sum + Number(index.index_size_bytes || 0), 0);
  const candidateBytes = candidatesToClean.value.reduce((sum, run) => sum + Number(run.index_size_bytes || 0), 0);
  return activeBytes + candidateBytes;
});

const comparisonPlot = computed<PlotlyPayload | null>(() => {
  if (!successfulRuns.value.length) return null;
  const maxSize = Math.max(...successfulRuns.value.map((run) => Number(run.index_size_bytes || 0)), 1);
  const colors: Record<string, string> = { hnswlib_hnsw: "#2563eb", hnswlib_rp_hnsw: "#8b5cf6", faiss_ivf_flat: "#059669", faiss_ivf_pq: "#f97316" };
  return {
    data: [{
      type: "scatter",
      mode: "markers+text",
      x: successfulRuns.value.map((run) => run.p95_query_time_ms || 0),
      y: successfulRuns.value.map((run) => (run.recall_at_k || 0) * 100),
      text: successfulRuns.value.map((run) => run.name),
      textposition: "top center",
      hovertemplate: successfulRuns.value.map((run) => `${run.name}<br>Recall %{y:.1f}%<br>P95 %{x:.4f} ms<br>体积 ${formatBytes(run.index_size_bytes)}<extra></extra>`),
      marker: {
        size: successfulRuns.value.map((run) => 16 + Math.sqrt(Number(run.index_size_bytes || 0) / maxSize) * 20),
        color: successfulRuns.value.map((run) => colors[run.algorithm] || "#64748b"),
        opacity: 0.82,
        line: { color: "#ffffff", width: 1.5 },
      },
    }],
    layout: {
      title: { text: "质量越高、越靠左越好" },
      showlegend: false,
      xaxis: { title: "P95 查询耗时 (ms)" },
      yaxis: { title: `Recall@${experimentResult.value?.top_k || 10} (%)`, range: [0, 103] },
      margin: { l: 58, r: 24, t: 52, b: 54 },
      shapes: [
        { type: "line", x0: 0, x1: 1, xref: "paper", y0: 90, y1: 90, line: { color: "#94a3b8", dash: "dot" } },
        { type: "line", x0: 0, x1: 1, xref: "paper", y0: 95, y1: 95, line: { color: "#059669", dash: "dot" } },
      ],
    },
  };
});

function recommendationTags(value?: string | null) { return (value || "").split(",").map((item) => item.trim()).filter(Boolean); }
function fixed(value?: number | null) { return typeof value === "number" ? value.toFixed(4) : "-"; }
function percent(value?: number | null) { return typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "-"; }
function formatBytes(value?: number | null) { if (!value) return "-"; if (value < 1024) return `${value} B`; if (value < 1048576) return `${(value / 1024).toFixed(1)} KB`; return `${(value / 1048576).toFixed(1)} MB`; }
function algorithmShort(value: string) { return value.replace("hnswlib_", "").replace("faiss_", "").replace(/_/g, " ").toUpperCase(); }
function paramsSummary(params?: Record<string, unknown>) { const entries = Object.entries(params || {}); return entries.length ? entries.map(([key, value]) => `${key}=${value}`).join(", ") : "默认参数"; }
function selectionText(labels?: string[]) { return labels?.length ? labels.map((label) => recommendationText(label)).join(" · ") : "手动保留"; }
function defaultParams(algorithm: string, overrides: Record<string, number | string> = {}) { return { ...(algorithms.value.find((item) => item.key === algorithm)?.default_params || {}), ...overrides }; }

function resetCandidates() {
  const defaults: IndexCandidateConfig[] = [
    { key: "hnsw_fast", name: "HNSW fast", algorithm: "hnswlib_hnsw", params: defaultParams("hnswlib_hnsw", { M: 8, ef_construction: 80, ef_search: 32 }) },
    { key: "hnsw_balanced", name: "HNSW balanced", algorithm: "hnswlib_hnsw", params: defaultParams("hnswlib_hnsw", { M: 16, ef_construction: 200, ef_search: 100 }) },
    { key: "hnsw_high_recall", name: "HNSW high recall", algorithm: "hnswlib_hnsw", params: defaultParams("hnswlib_hnsw", { M: 32, ef_construction: 300, ef_search: 220 }) },
    { key: "rp_hnsw", name: "RP-HNSW", algorithm: "hnswlib_rp_hnsw", params: defaultParams("hnswlib_rp_hnsw", { projection_dim: 16, random_state: 42, M: 12, ef_construction: 120, ef_search: 64 }) },
    { key: "faiss_ivf_flat", name: "FAISS IVF-Flat", algorithm: "faiss_ivf_flat", params: defaultParams("faiss_ivf_flat") },
    { key: "faiss_ivf_pq_compact", name: "FAISS IVF-PQ compact", algorithm: "faiss_ivf_pq", params: defaultParams("faiss_ivf_pq", { nbits: 4 }) },
  ];
  candidates.value = defaults.map((item) => ({ ...item, paramsText: JSON.stringify(item.params, null, 2) }));
}

function addCandidate() {
  const algorithm = candidateAlgorithmOptions.value[0]?.value || "hnswlib_hnsw";
  const params = defaultParams(algorithm);
  candidates.value.push({ key: `custom_${Date.now()}`, name: `自定义 ${algorithmShort(algorithm)}`, algorithm, params, paramsText: JSON.stringify(params, null, 2) });
}
function duplicateCandidate(candidate: CandidateDraft) { if (candidates.value.length < 12) candidates.value.push({ ...candidate, key: `${candidate.key}_${Date.now()}`, name: `${candidate.name} 副本` }); }
function removeCandidate(key: string) { candidates.value = candidates.value.filter((item) => item.key !== key); }
function changeCandidateAlgorithm(candidate: CandidateDraft) { const params = defaultParams(candidate.algorithm); candidate.params = params; candidate.paramsText = JSON.stringify(params, null, 2); }

function normalizedCandidateConfigs(): IndexCandidateConfig[] {
  return candidates.value.map((candidate) => {
    let params: unknown;
    try { params = JSON.parse(candidate.paramsText || "{}"); } catch { throw new Error(`${candidate.name} 的参数不是有效 JSON`); }
    if (!params || Array.isArray(params) || typeof params !== "object") throw new Error(`${candidate.name} 的参数必须是 JSON 对象`);
    return { key: candidate.key, name: candidate.name.trim(), algorithm: candidate.algorithm, params: params as Record<string, number | string> };
  });
}

function selectionDisabled(run: IndexExperimentRun) {
  if (experimentResult.value?.status !== "ready_for_selection") return true;
  if (run.status !== "success" || (run.recall_at_k || 0) < 0.80) return true;
  return !selectedRunIds.value.includes(run.id) && selectedRunIds.value.length >= 3;
}
function onRunSelectionChange(run: IndexExperimentRun, event: { target: { checked: boolean } }) {
  if (event.target.checked) {
    if (!selectedRunIds.value.includes(run.id) && selectedRunIds.value.length < 3) selectedRunIds.value.push(run.id);
  } else {
    selectedRunIds.value = selectedRunIds.value.filter((id) => id !== run.id);
  }
}

async function loadAlgorithms() {
  const data = await api.annAlgorithms(selectedDatasetId.value);
  algorithms.value = data.algorithms;
  resetCandidates();
}
async function loadExperiments() {
  historyLoading.value = true;
  try { experiments.value = (await api.indexExperiments(selectedDatasetId.value)).experiments; } finally { historyLoading.value = false; }
}
async function loadExperimentDetail(id: number, initializeSelection = false) {
  const data = await api.indexExperiment(id);
  experimentResult.value = data.experiment;
  const shouldInitialize = initializeSelection || selectionExperimentId !== id || (data.experiment.status === "ready_for_selection" && !selectedRunIds.value.length);
  if (shouldInitialize) {
    selectedRunIds.value = data.experiment.selected_run_ids.length ? [...data.experiment.selected_run_ids] : [...data.experiment.recommended_run_ids].slice(0, 3);
    selectionExperimentId = id;
  }
}

async function onDatasetChange() {
  experimentResult.value = null;
  selectedRunIds.value = [];
  selectionExperimentId = undefined;
  if (!selectedDatasetId.value) return;
  await Promise.all([store.loadDetail(selectedDatasetId.value), loadAlgorithms(), loadExperiments()]);
  const latestV2 = experiments.value.find((item) => item.workflow_version >= 2);
  if (latestV2) await loadExperimentDetail(latestV2.id, true);
}

async function startExperiment() {
  if (!selectedDatasetId.value) return;
  experimentRunning.value = true;
  currentTask.value = null;
  try {
    const data = await api.indexExperimentTask({
      dataset_id: selectedDatasetId.value,
      metric: form.metric,
      top_k: form.top_k,
      sample_size: form.sample_size,
      seed: form.seed,
      repetitions: form.repetitions,
      warmup_count: form.warmup_count,
      candidate_configs: normalizedCandidateConfigs(),
    });
    selectionExperimentId = data.experiment_id;
    selectedRunIds.value = [];
    await loadExperiments();
    await loadExperimentDetail(data.experiment_id, true);
    const task = await taskStore.waitForTask(data.task_id, (nextTask) => {
      currentTask.value = nextTask;
      void loadExperimentDetail(data.experiment_id);
    }, { timeoutMs: 1_800_000 });
    const payload = task.result as { experiment?: IndexExperiment } | null;
    if (payload?.experiment) experimentResult.value = payload.experiment;
    await Promise.all([loadExperimentDetail(data.experiment_id), loadExperiments(), store.loadDetail(selectedDatasetId.value)]);
    message.success("候选索引构建与真实评估完成");
  } catch (error) {
    message.error((error as Error).message);
    await loadExperiments().catch(() => undefined);
  } finally {
    experimentRunning.value = false;
  }
}

async function finalizeSelection() {
  if (!experimentResult.value || !selectedDatasetId.value) return;
  finalizing.value = true;
  try {
    await api.finalizeIndexExperiment(experimentResult.value.id, selectedRunIds.value);
    finalizeOpen.value = false;
    await Promise.all([loadExperimentDetail(experimentResult.value.id, true), loadExperiments(), store.loadDetail(selectedDatasetId.value)]);
    message.success("最终索引保留集合已生效，其它索引文件已清理");
  } catch (error) {
    message.error((error as Error).message);
  } finally {
    finalizing.value = false;
  }
}

function confirmDiscard() {
  if (!experimentResult.value) return;
  Modal.confirm({
    title: `放弃实验 #${experimentResult.value.id}？`,
    content: "候选物理文件将立即清理，实验配置和指标仍会保留。",
    okText: "放弃并清理",
    okType: "danger",
    async onOk() {
      if (!experimentResult.value || !selectedDatasetId.value) return;
      await api.discardIndexExperiment(experimentResult.value.id);
      await Promise.all([loadExperimentDetail(experimentResult.value.id, true), loadExperiments(), store.loadDetail(selectedDatasetId.value)]);
      message.success("实验已放弃并完成清理");
    },
  });
}

async function retryCleanup() {
  if (!experimentResult.value) return;
  try {
    await api.cleanupIndexExperiment(experimentResult.value.id);
    await loadExperimentDetail(experimentResult.value.id);
    message.success("清理重试完成");
  } catch (error) { message.error((error as Error).message); }
}
async function openHistoryExperiment(id: number) { await loadExperimentDetail(id, true); historyOpen.value = false; }
function goToQuery() { if (selectedDatasetId.value) router.push(`/query-lab?dataset=${selectedDatasetId.value}`); }

onMounted(async () => {
  await store.loadAll();
  selectedDatasetId.value = Number(route.query.dataset) || store.datasets[0]?.id;
  if (selectedDatasetId.value) await onDatasetChange();
  pollingTimer = window.setInterval(() => {
    if (experimentResult.value && ["pending", "running"].includes(experimentResult.value.status)) void loadExperimentDetail(experimentResult.value.id);
  }, 2000);
});
onBeforeUnmount(() => { if (pollingTimer) window.clearInterval(pollingTimer); });
</script>

<style scoped>
.retained-strip { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 18px; padding: 14px 16px; }
.retained-copy { display: grid; gap: 2px; }
.retained-copy strong { color: #172033; font-size: 16px; }
.retained-copy span:last-child, .eyebrow { color: #64748b; font-size: 12px; }
.eyebrow { font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.retained-list { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.retained-chip { display: grid; min-width: 126px; padding: 7px 10px; border: 1px solid #dbe5f0; border-radius: 8px; background: #f8fbff; }
.retained-chip span { color: #1e3a5f; font-size: 12px; font-weight: 700; }
.retained-chip small { color: #64748b; }
.config-panel, .progress-panel, .result-panel { margin-bottom: 18px; padding: 18px; }
.section-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 18px; }
.section-head > div:first-child { display: flex; gap: 12px; }
.section-head h2 { margin: 0; color: #172033; font-size: 18px; }
.section-head p { margin: 3px 0 0; color: #64748b; font-size: 12px; }
.compact-head { margin-bottom: 14px; }
.step-label { display: grid; flex: 0 0 auto; width: 34px; height: 34px; place-items: center; border-radius: 10px; background: #eaf2ff; color: #2563eb; font-size: 12px; font-weight: 800; }
.step-label.done { background: #dcfce7; color: #059669; }
.config-grid { display: grid; grid-template-columns: 1fr .55fr 1.1fr 1.1fr auto; gap: 12px; align-items: stretch; }
.config-field, .config-summary { display: grid; align-content: center; gap: 5px; min-height: 78px; padding: 10px 12px; border: 1px solid #e5eaf2; border-radius: 8px; background: #fbfcfe; }
.config-field > span, .config-summary > span { color: #64748b; font-size: 11px; }
.config-summary strong { color: #172033; font-size: 14px; }
.config-summary small { color: #64748b; }
.config-field :deep(.ant-input-number) { width: 100%; }
.config-actions { display: flex; align-items: center; gap: 8px; }
.config-alert { margin-top: 12px; }
.run-status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 8px; margin-top: 14px; }
.run-status-card { display: grid; grid-template-columns: auto 1fr; gap: 4px 8px; padding: 10px; border: 1px solid #e5eaf2; border-radius: 8px; }
.run-status-card small { grid-column: 2; overflow: hidden; color: #64748b; text-overflow: ellipsis; white-space: nowrap; }
.result-stack { display: grid; gap: 16px; }
.baseline-bar { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 14px; }
.baseline-bar > div { display: grid; gap: 3px; padding: 10px 12px; border-radius: 8px; background: #f5f8fc; }
.baseline-bar span { color: #64748b; font-size: 11px; }
.baseline-bar strong { color: #172033; }
.comparison-layout { display: grid; grid-template-columns: minmax(0, 1.65fr) minmax(250px, .72fr); gap: 14px; margin-bottom: 16px; }
.chart-card, .shortlist-card { min-width: 0; padding: 12px; border: 1px solid #e5eaf2; border-radius: 9px; background: #fff; }
.card-title { color: #172033; font-weight: 800; }
.shortlist-card > p { margin: 4px 0 12px; color: #64748b; font-size: 12px; }
.shortlist-items { display: grid; gap: 8px; margin-bottom: 10px; }
.shortlist-item { display: grid; gap: 7px; padding: 10px; border: 1px solid #dbeafe; border-left: 4px solid #2563eb; border-radius: 8px; background: #f8fbff; }
.shortlist-item > div:first-child { display: flex; justify-content: space-between; gap: 8px; }
.shortlist-item small { color: #64748b; }
.tag-row { display: flex; flex-wrap: wrap; gap: 4px; }
.comparison-table { border: 1px solid #e5eaf2; border-radius: 8px; overflow: hidden; }
.candidate-cell { display: grid; }
.candidate-cell small { color: #64748b; }
.expanded-detail { display: grid; gap: 5px; color: #475569; font-size: 12px; }
.finalize-bar, .completed-panel { position: sticky; bottom: 14px; z-index: 8; display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 16px; box-shadow: 0 12px 30px rgba(15, 23, 42, .12); }
.finalize-bar > div, .completed-panel > div { display: flex; align-items: center; gap: 10px; }
.finalize-bar strong, .completed-panel strong { display: block; color: #172033; }
.finalize-bar small, .completed-panel small { display: block; color: #64748b; }
.advanced-fields { margin-top: 18px; }
.advanced-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.advanced-grid :deep(.ant-input-number) { width: 100%; }
.candidate-editor-head { display: flex; align-items: center; justify-content: space-between; margin: 8px 0 10px; }
.candidate-editor-card { display: grid; gap: 8px; margin-bottom: 10px; padding: 10px; border: 1px solid #e5eaf2; border-radius: 8px; }
.candidate-editor-row { display: grid; grid-template-columns: 1fr 1fr auto auto; gap: 8px; }
.confirm-group { margin-top: 16px; }
.confirm-group ul { margin: 6px 0 0; padding-left: 22px; color: #475569; }
.reclaim-total { margin-top: 16px; padding: 10px 12px; border-radius: 8px; background: #eff6ff; color: #1e3a8a; }
@media (max-width: 1120px) { .config-grid { grid-template-columns: repeat(2, 1fr); } .config-actions { grid-column: 1 / -1; justify-content: flex-end; } .comparison-layout { grid-template-columns: 1fr; } }
@media (max-width: 720px) { .retained-strip, .section-head, .finalize-bar, .completed-panel { align-items: flex-start; flex-direction: column; } .retained-list { justify-content: flex-start; } .config-grid, .baseline-bar, .advanced-grid { grid-template-columns: 1fr; } .candidate-editor-row { grid-template-columns: 1fr; } }
</style>
