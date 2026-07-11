<template>
  <div :class="['global-assistant', { workspace: embedded }]">
    <aside v-if="embedded || historyOpen" :class="['assistant-history', { floating: !embedded }]">
      <div class="history-head">
        <strong>助手会话</strong>
        <div class="history-actions">
          <a-button size="small" :loading="creating" @click="newConversation">新建</a-button>
          <a-button v-if="!embedded" size="small" type="text" @click="historyOpen = false">收起</a-button>
        </div>
      </div>
      <a-empty v-if="!loading && !conversations.length" description="暂无会话" />
      <a-list size="small" :data-source="conversations" :loading="loading">
        <template #renderItem="{ item }">
          <a-list-item :class="{ active: item.id === conversationId }" @click="openConversation(item.id)">
            <a-list-item-meta :title="item.title" />
            <template #actions>
              <a-popconfirm title="删除这个会话及其消息？" ok-text="删除" cancel-text="取消" @confirm="deleteConversation(item.id)">
                <a-button type="text" size="small" danger :loading="deletingId === item.id" @click.stop>删除</a-button>
              </a-popconfirm>
            </template>
          </a-list-item>
        </template>
      </a-list>
    </aside>

    <section class="assistant-main">
      <header class="assistant-head">
        <div><strong>AI 助手</strong><small>平台问答、自然语言操作与科学分析</small></div>
        <div class="head-actions">
          <a-select v-model:value="modelId" size="small" style="min-width:150px" :options="modelOptions" />
          <a-button v-if="!embedded" size="small" @click="historyOpen = true">会话</a-button>
          <a-button v-if="!embedded" size="small" @click="$router.push('/ai-assistant')">完整工作台</a-button>
          <a-button v-else size="small" :loading="creating" @click="newConversation">新建会话</a-button>
        </div>
      </header>

      <div class="context-strip">
        <a-switch v-model:checked="contextEnabled" size="small" />
        <span>使用页面上下文</span>
        <a-tag v-if="contextEnabled" closable @close.prevent="contextEnabled = false">{{ contextLabel }}</a-tag>
      </div>

      <div ref="messagePane" class="assistant-messages">
        <a-empty v-if="!messages.length" description="可以直接提问，也可以描述要完成的单细胞检索或跨数据集分析" />
        <article v-for="item in messages" v-show="!isPlanMessage(item)" :key="item.id" :class="['assistant-message', item.role, { result: isAnalysisResult(item) }]">
          <small>{{ item.role === 'user' ? '你' : 'AI 助手' }}</small>
          <template v-if="isAnalysisResult(item)">
            <div class="result-head">
              <strong>{{ analysisSummary(item)?.headline || '分析结果' }}</strong>
              <a-tag color="green">分析完成</a-tag>
            </div>
            <div class="message-content">{{ analysisDisplayText(item) }}</div>
            <a-button v-if="analysisFullText(item).length > 900" type="link" size="small" @click="toggleExpanded(item.id)">
              {{ expandedMessages.has(item.id) ? '收起完整分析' : '展开完整分析' }}
            </a-button>
            <div v-if="analysisTaskIds(item).length" class="result-actions">
              <a-button v-for="taskId in analysisTaskIds(item)" :key="taskId" size="small" type="primary" ghost @click="openQueryLab(taskId)">
                在 Query Lab 查看结果
              </a-button>
            </div>
            <a-collapse v-if="analysisEvidenceEntries(item).length || item.citations?.length" ghost class="evidence-collapse">
              <a-collapse-panel key="evidence" header="分析详情（可选）">
                <div v-if="analysisEvidenceEntries(item).length" class="evidence-grid">
                  <div v-for="entry in analysisEvidenceEntries(item)" :key="entry.key">
                    <span>{{ entry.label }}</span><strong>{{ entry.value }}</strong>
                  </div>
                </div>
                <div v-if="item.citations?.length" class="assistant-citations">
                  <a-tag v-for="citation in item.citations" :key="citation.key">{{ citation.source_title }}</a-tag>
                </div>
              </a-collapse-panel>
            </a-collapse>
          </template>
          <div v-else class="message-content">{{ cleanAnswerText(item.content) }}</div>
          <template v-if="assistantAction(item)">
            <a-card size="small" class="action-card" title="待确认的平台操作">
              <p><strong>{{ actionName(assistantAction(item)?.name) }}</strong></p>
              <p>{{ assistantAction(item)?.impact }}</p>
              <a-descriptions size="small" :column="1" bordered>
                <a-descriptions-item v-for="(value, key) in assistantAction(item)?.args" :key="key" :label="String(key)">{{ displayValue(value) }}</a-descriptions-item>
              </a-descriptions>
              <div class="action-buttons">
                <template v-if="toolStatus(Number(assistantAction(item)?.tool_call_id)) === 'proposed'">
                  <a-button type="primary" size="small" :loading="actionLoading" @click="approveAction(Number(assistantAction(item)?.tool_call_id))">确认执行</a-button>
                  <a-button size="small" danger :loading="actionLoading" @click="rejectAction(Number(assistantAction(item)?.tool_call_id))">拒绝</a-button>
                </template>
                <a-tag v-else :color="toolStatus(Number(assistantAction(item)?.tool_call_id)) === 'success' ? 'green' : 'default'">{{ toolStatus(Number(assistantAction(item)?.tool_call_id)) }}</a-tag>
              </div>
            </a-card>
          </template>
          <a-button v-if="clientAction(item)" size="small" type="link" @click="navigate(clientAction(item)!)">
            {{ clientAction(item)?.target === 'ai_analysis' ? '继续科学分析' : '打开相关页面' }}
          </a-button>
          <a-collapse v-if="!isAnalysisResult(item) && item.citations?.length" ghost class="evidence-collapse">
            <a-collapse-panel key="citations" header="参考资料（可选）">
              <div class="assistant-citations">
                <a-tag v-for="citation in item.citations" :key="citation.key">{{ citation.source_title }}</a-tag>
              </div>
            </a-collapse-panel>
          </a-collapse>
        </article>
        <article v-if="streamingText" class="assistant-message assistant streaming">
          <small>AI 助手 <a-tag color="processing">正在生成</a-tag></small>
          <div class="message-content">{{ cleanStreamingText(streamingText) }}<span class="stream-cursor">▍</span></div>
        </article>
        <a-card v-if="currentRun && !terminal(currentRun)" size="small" class="run-card">
          <a-spin v-if="['queued', 'planning', 'executing'].includes(currentRun.status)" size="small" />
          <a-tag v-else color="orange">{{ runStatusText(currentRun) }}</a-tag>
          {{ runActivityText(currentRun) }}
          <a-button v-if="currentRun.can_cancel" size="small" type="link" danger @click="cancelRun">
            {{ ['pending', 'running'].includes(currentRun.summary_status) && currentRun.status === 'success' ? '停止优化' : '取消' }}
          </a-button>
        </a-card>
        <section v-if="showAnalysisPlan" class="analysis-plan-card">
          <div class="plan-head"><strong>准备开始分析</strong><a-tag color="orange">确认后开始检索</a-tag></div>
          <p>{{ activePlan?.goal || '单细胞相似性检索与证据分析' }}</p>
          <div class="plan-facts">
            <a-tag>{{ planModeLabel }}</a-tag>
            <a-tag>{{ primaryPlanStep?.dataset_name || '待选择数据集' }}</a-tag>
            <a-tag>Cell #{{ primaryPlanStep?.query_cell_index ?? '-' }}</a-tag>
            <a-tag>Top {{ primaryPlanStep?.top_k || 10 }}</a-tag>
            <a-tag v-if="primaryPlanStep?.filter_cell_type">{{ primaryPlanStep.filter_cell_type }}</a-tag>
          </div>
          <a-alert v-if="activePlan?.validation_errors?.length" type="warning" show-icon
            message="计划还需要补充参数" :description="activePlan.validation_errors.join('；')" />
          <div class="plan-actions">
            <a-button @click="openPlanEditor">调整参数</a-button>
            <a-button type="primary" :loading="planApproving" :disabled="currentRun?.status !== 'awaiting_confirmation'" @click="approveAnalysisPlan">确认并执行</a-button>
            <a-button danger @click="rejectAnalysisPlan">取消计划</a-button>
          </div>
        </section>
      </div>

      <footer class="assistant-composer">
        <a-textarea v-model:value="prompt" :rows="embedded ? 3 : 2" :maxlength="4000" :disabled="conversationBusy"
          placeholder="提问平台功能，或描述单细胞检索、跨数据集分析和结果追问" @keydown.ctrl.enter.prevent="send" />
        <div><span class="muted">{{ conversationBusy ? '请先完成或取消当前计划' : 'Ctrl + Enter 发送 · 检索和写操作执行前都会确认' }}</span><a-button type="primary" :loading="sending" :disabled="conversationBusy || !prompt.trim() || !modelId" @click="send">发送</a-button></div>
      </footer>
    </section>

    <a-modal v-model:open="planEditorOpen" title="调整科学分析参数" ok-text="保存并校验" :confirm-loading="planSaving" @ok="saveAnalysisPlan">
      <a-form layout="vertical">
        <a-form-item label="检索模式"><a-select v-model:value="planForm.mode" :options="modeOptions" /></a-form-item>
        <a-form-item label="查询数据集"><a-select v-model:value="planForm.dataset_id" :options="datasetOptions" @change="onPlanDatasetChange" /></a-form-item>
        <a-form-item v-if="planForm.mode !== 'joint'" label="源索引"><a-select v-model:value="planForm.index_id" :options="planIndexOptions" /></a-form-item>
        <a-form-item v-else label="联合索引"><a-select v-model:value="planForm.joint_index_id" :options="jointIndexOptions" /></a-form-item>
        <a-form-item v-if="planForm.mode !== 'single'" label="目标数据集"><a-select v-model:value="planForm.target_dataset_ids" mode="multiple" :options="datasetOptions" /></a-form-item>
        <a-form-item label="查询细胞编号"><a-input-number v-model:value="planForm.query_cell_index" :min="0" style="width:100%" /></a-form-item>
        <a-form-item label="Top-K"><a-input-number v-model:value="planForm.top_k" :min="1" :max="100" style="width:100%" /></a-form-item>
        <a-form-item label="细胞类型过滤"><a-select v-model:value="planForm.filter_cell_type" allow-clear :options="cellTypeOptions" placeholder="不限制" /></a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { message } from "ant-design-vue";
import { api } from "@/services/api";
import { analysisModeForTool, toolForAnalysisMode } from "@/services/ai-stream";
import { useDatasetStore } from "@/stores/datasets";
import type {
  AiAnalysisPlan, AiAnalysisStep, AiAnalysisSummary, AiAssistantClientAction,
  AiConversation, AiMessage, AiModelConfig, AiRun, JointIndex,
} from "@/types";

const props = defineProps<{ embedded?: boolean }>();

const route = useRoute();
const router = useRouter();
const datasetsStore = useDatasetStore();
const conversations = ref<AiConversation[]>([]);
const messages = ref<AiMessage[]>([]);
const runs = ref<AiRun[]>([]);
const models = ref<AiModelConfig[]>([]);
const conversationId = ref<number>();
const modelId = ref<number>();
const prompt = ref("");
const contextEnabled = ref(true);
const loading = ref(false);
const sending = ref(false);
const actionLoading = ref(false);
const creating = ref(false);
const deletingId = ref<number>();
const historyOpen = ref(false);
const currentRun = ref<AiRun | null>(null);
const streamingText = ref("");
const streamStage = ref("");
const expandedMessages = ref(new Set<number>());
const jointIndexes = ref<JointIndex[]>([]);
const cellTypes = ref<string[]>([]);
const planEditorOpen = ref(false);
const planSaving = ref(false);
const planApproving = ref(false);
const messagePane = ref<HTMLElement>();
let source: EventSource | null = null;
let pollTimer: number | null = null;
let reconnectTimer: number | null = null;
let realtimeRunId: number | null = null;
let lastEventId = 0;
let reconnectAttempts = 0;

const modelOptions = computed(() => models.value.map((item) => ({ value: item.id, label: item.display_name })));
const conversationBusy = computed(() => Boolean(currentRun.value && !terminal(currentRun.value)));
const activePlan = computed<AiAnalysisPlan | null>(() => {
  const plan = currentRun.value?.plan;
  return plan && Array.isArray((plan as AiAnalysisPlan).steps) ? plan as AiAnalysisPlan : null;
});
const primaryPlanStep = computed<AiAnalysisStep | null>(() => {
  if (activePlan.value) return activePlan.value.steps.find((step) => step.tool.startsWith("run_")) || null;
  const plan = currentRun.value?.plan;
  return plan ? ({ ...plan, tool: "run_single_cell_search" } as unknown as AiAnalysisStep) : null;
});
const showAnalysisPlan = computed(() => Boolean(
  currentRun.value?.surface === "analysis"
  && currentRun.value.plan
  && ["needs_input", "awaiting_confirmation"].includes(currentRun.value.status),
));
const planModeLabel = computed(() => ({ single: "单数据集", fanout: "Fan-out", joint: "联合索引" } as Record<string, string>)[
  analysisModeForTool(primaryPlanStep.value?.tool)
] || "单数据集");
const datasetOptions = computed(() => datasetsStore.indexedDatasets.map((item) => ({ value: item.id, label: item.name })));
const selectedPlanDataset = computed(() => datasetsStore.datasets.find((item) => item.id === planForm.dataset_id));
const planIndexOptions = computed(() => (selectedPlanDataset.value?.indexes || [])
  .filter((item) => item.status === "ready" && item.lifecycle === "active")
  .map((item) => ({ value: item.id, label: `${item.algorithm} · ${item.metric.toUpperCase()}` })));
const jointIndexOptions = computed(() => jointIndexes.value.filter((item) => item.status === "ready")
  .map((item) => ({ value: item.id, label: item.name })));
const cellTypeOptions = computed(() => cellTypes.value.map((value) => ({ value, label: value })));
const modeOptions = [
  { value: "single", label: "单数据集" },
  { value: "fanout", label: "Fan-out 跨数据集" },
  { value: "joint", label: "联合索引" },
];
const planForm = reactive<{
  mode: "single" | "fanout" | "joint";
  dataset_id?: number;
  index_id?: number;
  joint_index_id?: number;
  target_dataset_ids: number[];
  query_cell_index?: number;
  top_k: number;
  filter_cell_type?: string;
}>({ mode: "single", target_dataset_ids: [], top_k: 10 });
const pageContext = computed<Record<string, unknown>>(() => {
  const params = { ...route.params } as Record<string, unknown>;
  const query = { ...route.query } as Record<string, unknown>;
  const resources: Record<string, number> = {};
  const datasetValue = params.id || query.dataset;
  if (datasetValue && Number.isFinite(Number(datasetValue))) resources.dataset_id = Number(datasetValue);
  if (query.index && Number.isFinite(Number(query.index))) resources.index_id = Number(query.index);
  if (query.history_id && Number.isFinite(Number(query.history_id))) resources.history_id = Number(query.history_id);
  return { path: route.path, name: String(route.name || ""), params, query, resources, label: String(route.meta?.title || route.name || route.path) };
});
const contextLabel = computed(() => `当前：${String(route.name || route.path)}`);

function terminal(run: AiRun) { return ["success", "error", "rejected", "cancelled"].includes(run.status) && !["pending", "running"].includes(run.summary_status); }
function runStatusText(run: AiRun) {
  if (run.status === "success" && ["pending", "running"].includes(run.summary_status)) return "回答已就绪";
  return ({ needs_input: "需要补充", awaiting_confirmation: "等待确认", success: "已完成", error: "失败", cancelled: "已取消" } as Record<string, string>)[run.status] || run.status;
}
function runActivityText(run: AiRun) {
  if (run.status === "success" && ["pending", "running"].includes(run.summary_status)) return "正在优化简短解读，当前答案已经可以使用。";
  return streamStage.value || run.stage?.message || "AI 正在处理…";
}
function assistantAction(item: AiMessage) { return item.structured?.action as Record<string, unknown> | undefined; }
function clientAction(item: AiMessage) { return item.structured?.client_action as AiAssistantClientAction | undefined; }
function toolStatus(id: number) { return runs.value.flatMap((run) => run.tool_calls || []).find((tool) => tool.id === id)?.status || "proposed"; }
function displayValue(value: unknown) { return typeof value === "object" ? JSON.stringify(value) : String(value ?? "-"); }
function actionName(value: unknown) { return ({ submit_dataset_processing: "处理数据集", submit_index_build: "构建索引", submit_index_experiment: "运行索引实验", submit_index_evaluation: "评估索引", submit_joint_index_build: "构建联合索引", reindex_knowledge_document: "重建知识索引", create_personal_knowledge_note: "创建个人知识笔记" } as Record<string, string>)[String(value)] || String(value || "平台操作"); }
function isPlanMessage(item: AiMessage) { return ["analysis_plan", "search_plan"].includes(String(item.structured?.type || "")); }
function isAnalysisResult(item: AiMessage) { return ["analysis_result", "result_follow_up", "knowledge_answer"].includes(String(item.structured?.type || "")); }
function messageRun(item: AiMessage) { const id = Number(item.structured?.run_id); return runs.value.find((run) => run.id === id); }
function analysisSummary(item: AiMessage): AiAnalysisSummary | null {
  return (item.structured?.summary as AiAnalysisSummary | undefined) || messageRun(item)?.result?.summary || null;
}
function cleanAnswerText(value: unknown) {
  return String(value || "")
    .replace(/\[(?:E|K):[^\]]+\]/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
function cleanStreamingText(value: unknown) {
  return String(value || "")
    .replace(/\[(?:E|K):[^\]]*(?:\]|$)/g, "")
    .replace(/\n{3,}/g, "\n\n");
}
function analysisFullText(item: AiMessage) {
  const summary = analysisSummary(item);
  if (!summary) return cleanAnswerText(item.content);
  const [baseSummary, modelText] = String(summary.summary || "").split(/\n\n模型补充解读：\n?/);
  return cleanAnswerText([
    baseSummary,
    ...(summary.findings || []).slice(0, 4).map((finding) => finding.statement),
    modelText ? `简要解读：${modelText}` : "",
    ...(summary.caveats || []).slice(0, 1),
  ].filter(Boolean).join("\n"));
}
function analysisDisplayText(item: AiMessage) {
  const text = analysisFullText(item);
  return expandedMessages.value.has(item.id) || text.length <= 900 ? text : `${text.slice(0, 900).trim()}…`;
}
function toggleExpanded(id: number) {
  const next = new Set(expandedMessages.value);
  if (next.has(id)) next.delete(id); else next.add(id);
  expandedMessages.value = next;
}
function evidenceLabel(key: string) { return ({ result_count: "结果数", distance_range: "距离范围", same_type_count: "同类型数", same_type_fraction: "同类型比例", query_cell_type: "查询类型", disease_distribution: "疾病分布", age_group_distribution: "年龄分布", cell_type_distribution: "细胞类型分布", dataset_distribution: "数据集分布", query_time_ms: "检索耗时" } as Record<string, string>)[key] || key; }
function formatEvidence(value: unknown) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(4);
  if (typeof value === "object") return Object.entries(value as Record<string, unknown>).slice(0, 4).map(([key, item]) => `${key}: ${item}`).join("；");
  return String(value);
}
function analysisEvidenceEntries(item: AiMessage) {
  const evidence = messageRun(item)?.result?.evidence || {};
  const preferred = ["result_count", "distance_range", "same_type_fraction", "cell_type_distribution", "disease_distribution", "age_group_distribution", "dataset_distribution"];
  return preferred.filter((key) => evidence[key] !== undefined).slice(0, 6).map((key) => ({ key, label: evidenceLabel(key), value: formatEvidence(evidence[key]) }));
}
function analysisTaskIds(item: AiMessage) {
  const raw = item.structured?.search_task_ids;
  const values = Array.isArray(raw) ? raw : [item.structured?.search_task_id, messageRun(item)?.search_task_id];
  return [...new Set(values.map(Number).filter((value) => Number.isFinite(value) && value > 0))];
}

async function loadBase() {
  loading.value = true;
  try {
    const [modelData, conversationData] = await Promise.all([api.aiModels(), api.aiConversations("assistant")]);
    models.value = modelData.models;
    const savedModel = Number(localStorage.getItem("ai-model-config"));
    modelId.value ||= models.value.find((item) => item.id === savedModel)?.id || models.value.find((item) => item.is_default)?.id || models.value[0]?.id;
    conversations.value = conversationData.conversations;
    const requested = Number(route.query.conversation_id);
    const initial = conversations.value.find((item) => item.id === requested) || conversations.value[0];
    if (initial && initial.id !== conversationId.value) await openConversation(initial.id);
    if (typeof route.query.prompt === "string" && route.query.prompt.trim()) prompt.value = route.query.prompt.slice(0, 4000);
  } finally { loading.value = false; }
}

async function ensureConversation() {
  if (conversationId.value) return conversationId.value;
  const row = (await api.createAiConversation("新建全局助手会话", "assistant")).conversation;
  conversationId.value = row.id;
  conversations.value.unshift(row);
  return row.id;
}

async function openConversation(id: number) {
  stopRealtime();
  const detail = (await api.aiConversation(id)).conversation;
  conversationId.value = id;
  streamingText.value = "";
  streamStage.value = "";
  messages.value = detail.messages || [];
  runs.value = detail.runs || [];
  currentRun.value = [...runs.value].reverse().find((item) => !terminal(item)) || runs.value[runs.value.length - 1] || null;
  syncPlanForm(currentRun.value);
  if (currentRun.value && !terminal(currentRun.value)) startRealtime(currentRun.value);
  if (!props.embedded) historyOpen.value = false;
  if (props.embedded && Number(route.query.conversation_id) !== id) {
    await router.replace({ query: { ...route.query, conversation_id: String(id) } });
  }
  await scrollEnd();
}

async function newConversation() {
  if (creating.value) return;
  creating.value = true;
  try {
    stopRealtime();
    const row = (await api.createAiConversation("新建全局助手会话", "assistant")).conversation;
    conversations.value = [row, ...conversations.value.filter((item) => item.id !== row.id)];
    await openConversation(row.id);
    prompt.value = "";
  } catch (error) { message.error((error as Error).message); }
  finally { creating.value = false; }
}

async function deleteConversation(id: number) {
  if (deletingId.value) return;
  deletingId.value = id;
  try {
    await api.deleteAiConversation(id);
    conversations.value = conversations.value.filter((item) => item.id !== id);
    if (conversationId.value === id) {
      stopRealtime();
      conversationId.value = undefined;
      messages.value = [];
      runs.value = [];
      currentRun.value = null;
      streamingText.value = "";
      const next = conversations.value[0];
      if (next) await openConversation(next.id);
      else if (props.embedded) await router.replace({ query: { ...route.query, conversation_id: undefined } });
    }
    message.success("会话已删除");
  } catch (error) { message.error((error as Error).message); }
  finally { deletingId.value = undefined; }
}

async function refreshConversation() {
  if (!conversationId.value) return;
  const detail = (await api.aiConversation(conversationId.value)).conversation;
  messages.value = detail.messages || [];
  runs.value = detail.runs || [];
  const latest = runs.value[runs.value.length - 1];
  if (latest) { currentRun.value = latest; syncPlanForm(latest); }
  await scrollEnd();
}

async function send() {
  if (!prompt.value.trim() || !modelId.value) return;
  sending.value = true;
  try {
    const id = await ensureConversation();
    const content = prompt.value.trim();
    const data = await api.sendAssistantMessage(id, content, modelId.value, pageContext.value, contextEnabled.value);
    prompt.value = ""; currentRun.value = data.run; runs.value.push(data.run);
    await refreshConversation(); startRealtime(data.run);
    conversations.value = (await api.aiConversations("assistant")).conversations;
  } catch (error) { message.error((error as Error).message); }
  finally { sending.value = false; }
}

function syncPlanForm(run: AiRun | null) {
  if (!run?.plan) return;
  const analysis = Array.isArray((run.plan as AiAnalysisPlan).steps) ? run.plan as AiAnalysisPlan : null;
  const primary = analysis?.steps.find((step) => step.tool.startsWith("run_"));
  const source = primary || run.plan as unknown as AiAnalysisStep;
  Object.assign(planForm, {
    mode: analysisModeForTool(primary?.tool),
    dataset_id: source.dataset_id || (typeof source.dataset_reference === "number" ? source.dataset_reference : undefined),
    index_id: source.index_id || (typeof source.index_reference === "number" ? source.index_reference : undefined),
    joint_index_id: primary?.joint_index_id || undefined,
    target_dataset_ids: primary?.target_dataset_ids || [],
    query_cell_index: source.query_cell_index ?? undefined,
    top_k: source.top_k || 10,
    filter_cell_type: source.filter_cell_type || undefined,
  });
}

async function openPlanEditor() {
  try {
    const [, jointData] = await Promise.all([datasetsStore.loadAll(), api.jointIndexes()]);
    jointIndexes.value = jointData.joint_indexes;
    syncPlanForm(currentRun.value);
    if (planForm.dataset_id) cellTypes.value = (await api.cellTypes(planForm.dataset_id)).cell_types;
    planEditorOpen.value = true;
  } catch (error) { message.error((error as Error).message); }
}

async function onPlanDatasetChange() {
  planForm.index_id = planIndexOptions.value[0]?.value;
  cellTypes.value = planForm.dataset_id ? (await api.cellTypes(planForm.dataset_id)).cell_types : [];
  planForm.filter_cell_type = undefined;
}

async function saveAnalysisPlan() {
  if (!currentRun.value?.plan) return null;
  planSaving.value = true;
  try {
    let payload: Record<string, unknown>;
    if (activePlan.value) {
      const plan = activePlan.value;
      const steps = plan.steps.map((step) => step.tool.startsWith("run_") ? {
        ...step,
        tool: toolForAnalysisMode(planForm.mode),
        selection_mode: "explicit",
        dataset_reference: planForm.dataset_id,
        dataset_id: planForm.dataset_id,
        index_reference: planForm.index_id,
        index_id: planForm.index_id,
        joint_index_reference: planForm.joint_index_id,
        joint_index_id: planForm.joint_index_id,
        target_dataset_ids: planForm.target_dataset_ids,
        query_cell_index: planForm.query_cell_index,
        top_k: planForm.top_k,
        filter_cell_type: planForm.filter_cell_type || null,
      } : step);
      payload = { goal: plan.goal, response_language: plan.response_language, knowledge_scopes: plan.knowledge_scopes, expected_outputs: plan.expected_outputs, steps };
    } else {
      payload = { dataset_id: planForm.dataset_id, index_id: planForm.index_id, query_cell_index: planForm.query_cell_index, top_k: planForm.top_k, filter_cell_type: planForm.filter_cell_type || null };
    }
    const data = await api.updateAiRunPlan(currentRun.value.id, payload);
    currentRun.value = data.run;
    syncPlanForm(data.run);
    if (!data.valid) { message.warning("计划仍有需要修正的参数"); return data.run; }
    planEditorOpen.value = false;
    message.success("分析参数已校验");
    return data.run;
  } catch (error) { message.error((error as Error).message); return null; }
  finally { planSaving.value = false; }
}

async function approveAnalysisPlan() {
  if (!currentRun.value) return;
  planApproving.value = true;
  try {
    const saved = await saveAnalysisPlan();
    if (!saved || saved.status !== "awaiting_confirmation") return;
    const data = await api.approveAiRun(saved.id);
    currentRun.value = data.run;
    startRealtime(data.run);
  } catch (error) { message.error((error as Error).message); }
  finally { planApproving.value = false; }
}

async function rejectAnalysisPlan() {
  if (!currentRun.value) return;
  currentRun.value = (await api.rejectAiRun(currentRun.value.id)).run;
  await refreshConversation();
}

function openQueryLab(taskId: number) { void router.push({ path: "/query-lab", query: { history_id: String(taskId) } }); }

function startRealtime(run: AiRun) {
  stopRealtime();
  realtimeRunId = run.id;
  lastEventId = 0;
  reconnectAttempts = 0;
  streamingText.value = "";
  streamStage.value = run.stage?.message || "";
  if (typeof EventSource !== "undefined") connectRealtime(run);
  else startPolling(run.id);
}

function connectRealtime(run: AiRun) {
  if (realtimeRunId !== run.id) return;
  const separator = run.stream_url.includes("?") ? "&" : "?";
  source = new EventSource(lastEventId ? `${run.stream_url}${separator}after=${lastEventId}` : run.stream_url);
  const eventNames = [
    "run.stage", "plan.ready", "answer.started", "answer.delta", "answer.replace", "answer.completed",
    "action.proposed", "action.status", "ui.navigate", "assistant.handoff", "run.completed", "error",
  ];
  eventNames.forEach((name) => source?.addEventListener(name, async (event) => {
    if (realtimeRunId !== run.id) return;
    const messageEvent = event as MessageEvent;
    const sequence = Number(messageEvent.lastEventId);
    if (Number.isFinite(sequence) && sequence > lastEventId) lastEventId = sequence;
    const payload = JSON.parse(messageEvent.data || "{}");
    if (name === "run.stage") streamStage.value = String(payload.message || payload.label || "");
    if (name === "answer.started") streamingText.value = "";
    if (name === "answer.delta") {
      streamingText.value += String(payload.delta || "");
      await scrollEnd();
    }
    if (name === "ui.navigate" || name === "assistant.handoff") {
      if (payload.auto) await navigate(payload as AiAssistantClientAction);
    }
    if (["plan.ready", "answer.replace", "answer.completed", "action.proposed", "action.status", "run.completed", "error"].includes(name)) {
      await refreshConversation();
    }
    if (name === "answer.replace" || name === "answer.completed") streamingText.value = "";
    if (name === "run.completed" || name === "error") stopRealtime();
  }));
  source.onopen = () => { reconnectAttempts = 0; };
  source.onerror = () => {
    source?.close();
    source = null;
    if (realtimeRunId !== run.id) return;
    reconnectAttempts += 1;
    if (reconnectAttempts <= 2) {
      reconnectTimer = window.setTimeout(() => connectRealtime(run), 600);
    } else startPolling(run.id);
  };
}

function startPolling(runId: number) {
  if (pollTimer !== null) window.clearInterval(pollTimer);
  pollTimer = window.setInterval(async () => {
    const run = (await api.aiRun(runId)).run; currentRun.value = run; await refreshConversation();
    if (terminal(run)) stopRealtime();
  }, 1200);
}
function stopRealtime() {
  source?.close(); source = null;
  if (pollTimer !== null) window.clearInterval(pollTimer); pollTimer = null;
  if (reconnectTimer !== null) window.clearTimeout(reconnectTimer); reconnectTimer = null;
  realtimeRunId = null;
}

async function navigate(action: AiAssistantClientAction) {
  if (!action.path.startsWith("/")) return message.error("助手返回了无效页面地址");
  await router.push(action.path);
}
async function approveAction(id: number) { if (!id) return; actionLoading.value = true; try { await api.approveAiToolCall(id); message.success("平台任务已提交"); await refreshConversation(); } catch (error) { message.error((error as Error).message); } finally { actionLoading.value = false; } }
async function rejectAction(id: number) { if (!id) return; actionLoading.value = true; try { await api.rejectAiToolCall(id); message.info("操作已拒绝"); await refreshConversation(); } catch (error) { message.error((error as Error).message); } finally { actionLoading.value = false; } }
async function cancelRun() { if (!currentRun.value) return; await api.cancelAiRun(currentRun.value.id); await refreshConversation(); }
async function scrollEnd() { await nextTick(); if (messagePane.value) messagePane.value.scrollTop = messagePane.value.scrollHeight; }

watch(modelId, (value) => { if (value) localStorage.setItem("ai-model-config", String(value)); });
watch(() => route.query.conversation_id, (value) => {
  const id = Number(value); if (id && id !== conversationId.value) void openConversation(id);
});
watch(() => route.query.prompt, (value) => {
  if (typeof value === "string" && value.trim()) prompt.value = value.slice(0, 4000);
});
watch(() => route.fullPath, () => { /* computed context updates without retaining form secrets */ });
onMounted(loadBase);
onBeforeUnmount(stopRealtime);
</script>

<style scoped>
.global-assistant { position: relative; height: 100%; display: flex; min-height: 0; background: #f8fafc; overflow: hidden; }
.global-assistant.workspace { min-height: calc(100vh - 150px); border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; }
.assistant-history { width: 250px; background: white; border-right: 1px solid #e2e8f0; overflow: auto; }
.assistant-history.floating { position: absolute; inset: 0 auto 0 0; z-index: 20; width: min(310px, 82%); box-shadow: 8px 0 24px rgba(15, 23, 42, .16); }
.history-head, .assistant-head, .context-strip, .assistant-composer > div { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.history-actions { display: flex; align-items: center; gap: 4px; }
.history-head { padding: 14px; border-bottom: 1px solid #e2e8f0; }
.assistant-history :deep(.ant-list-item) { cursor: pointer; padding: 10px 14px; }
.assistant-history :deep(.ant-list-item.active) { background: #eff6ff; }
.assistant-main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.assistant-head { background: white; padding: 13px 16px; border-bottom: 1px solid #e2e8f0; }
.assistant-head small { display: block; color: #64748b; margin-top: 3px; }
.head-actions { display: flex; gap: 8px; }
.context-strip { justify-content: flex-start; padding: 8px 14px; background: #f1f5f9; font-size: 12px; color: #475569; }
.assistant-messages { flex: 1; overflow: auto; padding: 16px; min-height: 280px; }
.assistant-message { max-width: 88%; padding: 11px 13px; border-radius: 10px; margin-bottom: 12px; white-space: pre-wrap; }
.assistant-message.user { margin-left: auto; background: #dbeafe; }
.assistant-message.assistant { background: white; border: 1px solid #e2e8f0; }
.assistant-message.result { width: min(680px, 96%); max-width: 96%; }
.assistant-message.streaming { border-color: #93c5fd; box-shadow: 0 0 0 2px rgba(59, 130, 246, .06); }
.assistant-message small { color: #64748b; display: block; margin-bottom: 4px; }
.message-content { line-height: 1.65; }
.result-head, .plan-head, .plan-actions, .result-actions { display: flex; align-items: center; gap: 8px; }
.result-head, .plan-head { justify-content: space-between; margin-bottom: 8px; }
.result-actions, .plan-actions { margin-top: 12px; flex-wrap: wrap; }
.evidence-collapse { margin-top: 8px; border-top: 1px solid #f1f5f9; }
.evidence-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.evidence-grid > div { display: grid; gap: 2px; padding: 8px; border-radius: 8px; background: #f8fafc; }
.evidence-grid span { color: #64748b; font-size: 12px; }
.evidence-grid strong { font-size: 13px; overflow-wrap: anywhere; }
.stream-cursor { color: #2563eb; animation: blink 1s steps(1) infinite; }
.action-card { margin-top: 12px; white-space: normal; }
.action-buttons { display: flex; gap: 8px; margin-top: 12px; }
.assistant-citations { margin-top: 8px; }
.run-card { margin-top: 8px; }
.analysis-plan-card { margin: 10px 0; padding: 14px; border: 1px solid #fdba74; border-radius: 10px; background: #fffdf7; }
.analysis-plan-card p { margin: 8px 0; color: #334155; }
.plan-facts { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
.assistant-composer { padding: 12px 14px; background: white; border-top: 1px solid #e2e8f0; }
.assistant-composer > div { margin-top: 8px; }
.muted { color: #94a3b8; font-size: 12px; }
@keyframes blink { 50% { opacity: 0; } }
@media (max-width: 800px) { .assistant-history:not(.floating) { display: none; } .head-actions :deep(.ant-select) { display: none; } }
</style>
