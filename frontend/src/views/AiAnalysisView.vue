<template>
  <PageHeader title="AI 分析" description="用自然语言生成可确认的单细胞检索计划，并基于真实检索证据连续问答。">
    <template #actions>
      <a-space wrap>
        <a-select v-model:value="modelConfigId" :options="modelOptions" placeholder="选择管理员启用的模型" style="min-width:240px" />
        <a-button @click="$router.push('/ai-knowledge')">管理知识库</a-button>
        <a-button @click="newConversation">新建会话</a-button>
      </a-space>
    </template>
  </PageHeader>

  <a-alert v-if="modelsDisabled || !models.length" class="ai-alert" type="warning" show-icon
    message="当前没有可用 AI 模型" description="请联系管理员在“权限管理 → AI 模型”中配置、测试并启用模型。" />

  <div class="ai-workbench">
    <aside class="surface ai-history">
      <div class="history-head"><strong>分析会话</strong><a-button type="link" size="small" @click="loadConversations">刷新</a-button></div>
      <a-empty v-if="!conversations.length" description="暂无历史会话" />
      <div v-else class="history-list">
        <button v-for="item in conversations" :key="item.id" class="history-item" :class="{ active: item.id === conversationId }" @click="openConversation(item.id)">
          <span>{{ item.title }}</span><small>{{ formatDate(item.updated_at) }}</small>
        </button>
      </div>
      <a-popconfirm v-if="conversationId" title="删除当前 AI 会话及其关联检索历史？" @confirm="deleteConversation">
        <a-button block danger ghost>删除当前会话</a-button>
      </a-popconfirm>
    </aside>

    <main class="surface conversation-panel">
      <div class="toolbar"><span class="toolbar-title">AI 科学分析</span><a-tag color="blue">第二阶段 · RAG 与多模式检索</a-tag></div>

      <div ref="messageStream" class="message-stream">
        <div v-if="!messages.length" class="empty-prompt">
          <RobotOutlined class="empty-icon" />
          <strong>描述你希望完成的检索</strong>
          <span>可以检索平台资料，或生成单数据集、Fan-out、联合索引分析计划。</span>
        </div>
        <div v-for="item in messages" :key="item.id" class="message-row" :class="item.role">
          <div class="message-bubble" :class="{ 'result-bubble': isResultMessage(item) }">
            <small>{{ item.role === 'user' ? '你' : 'AI 分析' }}</small>
            <template v-if="isResultMessage(item) && messageSummary(item)">
              <div class="answer-head">
                <strong>{{ messageSummary(item)?.headline }}</strong>
                <a-tag :color="messageSummary(item)?.generated_by === 'model' ? 'purple' : 'blue'">
                  {{ messageSummary(item)?.generated_by === 'model' ? '模型增强' : '平台统计' }}
                </a-tag>
              </div>
              <p>{{ messageSummary(item)?.summary }}</p>
              <div v-for="finding in messageSummary(item)?.findings || []" :key="finding.statement" class="finding">
                <span>{{ finding.statement }}</span>
                <div class="evidence-tags">
                  <a-tag v-for="key in finding.evidence_keys" :key="key" color="blue">
                    {{ evidenceLabel(key) }}：{{ formatEvidence(messageEvidence(item)?.[key]) }}
                  </a-tag>
                </div>
              </div>
              <a-alert v-if="messageSummary(item)?.caveats?.length" type="info" show-icon
                :message="messageSummary(item)?.caveats.join('；')" />
              <a-space wrap style="margin-top:12px">
                <a-button v-if="messageSearchTaskId(item)" type="primary" size="small" @click="openQueryLab(messageSearchTaskId(item))">
                  在检索实验室查看完整结果
                </a-button>
              </a-space>
              <div v-if="item.citations?.length" class="citation-list">
                <strong>知识引用</strong>
                <a v-for="citation in item.citations" :key="citation.key" :href="citationUrl(citation.key)" target="_blank" class="citation-item">
                  {{ citation.source_title }}<template v-if="citation.page_number"> · 第 {{ citation.page_number }} 页</template>
                  <small>{{ citation.excerpt }}</small>
                </a>
              </div>
            </template>
            <div v-else class="plain-message">{{ item.content }}</div>
          </div>
        </div>

        <section v-if="currentRun" class="run-card">
          <div class="run-head">
            <strong>Run #{{ currentRun.id }}</strong>
            <a-space>
              <a-tag :color="runStatusColor(currentRun.status)">{{ runStatusLabel(currentRun.status) }}</a-tag>
              <a-tag v-if="['pending', 'running'].includes(currentRun.summary_status)" color="purple">解释增强中</a-tag>
              <a-tag v-else-if="currentRun.summary_status === 'fallback'">平台统计回答</a-tag>
              <a-button v-if="currentRun.can_cancel" size="small" danger ghost @click="cancelRun">停止</a-button>
            </a-space>
          </div>
          <a-steps size="small" :current="stepCurrent" :items="stepItems" />
          <a-alert v-if="currentRun.stage" class="stage-alert" :type="currentRun.status === 'error' ? 'error' : 'info'" show-icon
            :message="currentRun.stage.message || currentRun.stage.label" />
          <a-alert v-if="currentRun.error_message" type="error" show-icon :message="currentRun.error_message" :description="currentRun.error_code || undefined" />
          <div v-if="currentRun.summary_message" class="summary-status">{{ currentRun.summary_message }}</div>
          <div v-if="streamingEnhancement" class="streaming-answer">
            <div><span class="streaming-dot"></span><strong>模型实时补充解读</strong></div>
            <p>{{ streamingEnhancement }}</p>
          </div>
        </section>

        <section v-if="currentRun?.plan && ['needs_input', 'awaiting_confirmation'].includes(currentRun.status)" class="plan-card">
          <div class="plan-head"><strong>{{ isAnalysisPlan ? '多步骤分析计划' : '检索计划' }}</strong><a-tag color="orange">确认前不会执行 ANN</a-tag></div>
          <a-alert v-if="currentRun.plan.validation_errors?.length" type="warning" show-icon message="请修正以下参数"
            :description="currentRun.plan.validation_errors.join('；')" style="margin-bottom:12px" />
          <a-form layout="vertical">
            <div v-if="isAnalysisPlan" class="analysis-steps">
              <div v-for="(step, index) in analysisPlanSteps" :key="`${step.tool}-${index}`" class="analysis-step">
                <a-tag :color="step.tool.startsWith('run_') ? 'orange' : 'blue'">步骤 {{ index + 1 }}</a-tag>
                <strong>{{ toolLabel(step.tool) }}</strong>
                <span>{{ stepDescription(step) }}</span>
              </div>
            </div>
            <div class="plan-grid">
              <a-form-item v-if="isAnalysisPlan" label="检索模式">
                <a-select v-model:value="planForm.mode" :options="modeOptions" />
              </a-form-item>
              <a-form-item label="数据集"><a-select v-model:value="planForm.dataset_id" :options="datasetOptions" @change="onPlanDatasetChange" /></a-form-item>
              <a-form-item v-if="planForm.mode !== 'joint'" label="源索引"><a-select v-model:value="planForm.index_id" :options="planIndexOptions" /></a-form-item>
              <a-form-item v-else label="联合索引"><a-select v-model:value="planForm.joint_index_id" :options="jointIndexOptions" /></a-form-item>
              <a-form-item v-if="isAnalysisPlan && planForm.mode !== 'single'" label="目标数据集">
                <a-select v-model:value="planForm.target_dataset_ids" mode="multiple" :options="datasetOptions" placeholder="留空表示所有兼容数据集" />
              </a-form-item>
              <a-form-item label="查询细胞编号"><a-input-number v-model:value="planForm.query_cell_index" :min="0" :max="selectedPlanDataset?.n_cells ? selectedPlanDataset.n_cells - 1 : undefined" style="width:100%" /></a-form-item>
              <a-form-item label="Top-K"><a-input-number v-model:value="planForm.top_k" :min="1" :max="100" style="width:100%" /></a-form-item>
              <a-form-item label="细胞类型过滤"><a-select v-model:value="planForm.filter_cell_type" allow-clear :options="cellTypeOptions" placeholder="不限制" /></a-form-item>
            </div>
          </a-form>
          <a-space wrap>
            <a-button :loading="planSaving" @click="savePlan">保存并重新校验</a-button>
            <a-button type="primary" :loading="approving" :disabled="currentRun.status !== 'awaiting_confirmation'" @click="approve">确认并执行</a-button>
            <a-button danger @click="reject">拒绝</a-button>
          </a-space>
        </section>
      </div>

      <div class="composer">
        <a-textarea v-model:value="prompt" :maxlength="4000" show-count :rows="3"
          placeholder="输入检索需求，或继续询问上一轮结果。" @keydown.ctrl.enter="send" />
        <div class="knowledge-scopes">
          <span class="muted">知识来源</span>
          <a-checkbox-group v-model:value="knowledgeScopes" :options="knowledgeScopeOptions" />
        </div>
        <div class="composer-actions"><span class="muted">Ctrl + Enter 发送 · 默认中文回答</span><a-button type="primary"
          :disabled="!models.length || !modelConfigId" :loading="sending" @click="send">发送</a-button></div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { RobotOutlined } from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import PageHeader from "@/components/PageHeader.vue";
import { api } from "@/services/api";
import { analysisModeForTool, reduceAiStreamEvent, toolForAnalysisMode } from "@/services/ai-stream";
import { useDatasetStore } from "@/stores/datasets";
import { formatDate } from "@/utils/format";
import type { AiAnalysisPlan, AiAnalysisStep, AiAnalysisSummary, AiConversation, AiMessage, AiModelConfig, AiRun, JointIndex } from "@/types";

const router = useRouter();
const route = useRoute();
const datasetsStore = useDatasetStore();
const models = ref<AiModelConfig[]>([]);
const modelsDisabled = ref(false);
const modelConfigId = ref<number>();
const conversations = ref<AiConversation[]>([]);
const conversationId = ref<number>();
const messages = ref<AiMessage[]>([]);
const runs = ref<AiRun[]>([]);
const currentRun = ref<AiRun | null>(null);
const jointIndexes = ref<JointIndex[]>([]);
const toolCatalog = ref<Array<Record<string, unknown>>>([]);
const prompt = ref("");
const sending = ref(false);
const planSaving = ref(false);
const approving = ref(false);
const cellTypes = ref<string[]>([]);
const messageStream = ref<HTMLElement>();
let pollTimer: number | undefined;
let eventSource: EventSource | undefined;
let streamErrors = 0;
const streamingEnhancement = ref("");
const knowledgeScopes = ref<string[]>(["platform", "dataset", "personal"]);

const planForm = reactive<{ mode: "single" | "fanout" | "joint"; dataset_id?: number; index_id?: number; joint_index_id?: number; target_dataset_ids: number[]; query_cell_index?: number; top_k: number; filter_cell_type?: string }>({ mode: "single", target_dataset_ids: [], top_k: 10 });
const modelOptions = computed(() => models.value.map((item) => ({ value: item.id, label: `${item.display_name} · ${item.provider_name}${item.is_default ? '（默认）' : ''}` })));
const datasetOptions = computed(() => datasetsStore.indexedDatasets.map((item) => ({ value: item.id, label: `${item.name}（${item.n_cells || '?'} cells）` })));
const selectedPlanDataset = computed(() => datasetsStore.datasets.find((item) => item.id === planForm.dataset_id));
const planIndexOptions = computed(() => (selectedPlanDataset.value?.indexes || []).filter((item) => item.status === "ready" && item.lifecycle === "active").map((item) => ({ value: item.id, label: `${item.algorithm} · ${item.metric.toUpperCase()} · #${item.id}` })));
const cellTypeOptions = computed(() => cellTypes.value.map((value) => ({ value, label: value })));
const isAnalysisPlan = computed(() => Array.isArray((currentRun.value?.plan as AiAnalysisPlan | undefined)?.steps));
const analysisPlanSteps = computed(() => isAnalysisPlan.value ? ((currentRun.value?.plan as AiAnalysisPlan).steps || []) : []);
const modeOptions = [
  { value: "single", label: "单数据集" }, { value: "fanout", label: "Fan-out 跨数据集" },
  { value: "joint", label: "联合索引" },
];
const jointIndexOptions = computed(() => jointIndexes.value.filter((item) => item.status === "ready").map((item) => ({ value: item.id, label: `${item.name} · ${item.metric.toUpperCase()} · #${item.id}` })));
const knowledgeScopeOptions = [
  { value: "platform", label: "平台" }, { value: "dataset", label: "数据集" }, { value: "personal", label: "个人" },
];
const stepItems = computed(() => (currentRun.value?.timeline || []).map((item) => ({
  title: item.label,
  status: item.state === "done" || item.state === "skipped" ? "finish" : item.state === "active" ? "process" : item.state === "error" ? "error" : "wait",
})) as Array<{ title: string; status: "wait" | "process" | "finish" | "error" }>);
const stepCurrent = computed(() => Math.max(0, (currentRun.value?.timeline || []).findIndex((item) => item.state === "active")));

function runStatusLabel(status: string) { return ({ queued: "排队中", planning: "理解需求", needs_input: "需要补充参数", awaiting_confirmation: "等待确认", executing: "执行分析", streaming: "生成解读", success: "回答就绪", error: "失败", rejected: "已拒绝", cancelled: "已取消" } as Record<string, string>)[status] || status; }
function runStatusColor(status: string) { if (status === "success") return "green"; if (status === "error") return "red"; if (["awaiting_confirmation", "needs_input"].includes(status)) return "orange"; if (status === "rejected") return "default"; return "blue"; }
function evidenceLabel(key: string) { return ({ result_count: "结果数", distance_range: "距离范围", same_type_count: "同类型数", same_type_fraction: "同类型比例", query_cell_type: "查询类型", disease_distribution: "疾病分布", age_group_distribution: "年龄分布", cell_type_distribution: "类型分布", query_time_ms: "检索耗时", query_dataset: "数据集", query_cell_index: "查询细胞" } as Record<string, string>)[key] || key; }
function formatEvidence(value: unknown) { if (value === null || value === undefined || value === "") return "-"; return typeof value === "object" ? JSON.stringify(value) : String(value); }
function isResultMessage(item: AiMessage) { return ["analysis_result", "result_follow_up", "knowledge_answer"].includes(String(item.structured?.type || "")); }
function messageRun(item: AiMessage) { const id = Number(item.structured?.run_id); return runs.value.find((run) => run.id === id); }
function messageSummary(item: AiMessage): AiAnalysisSummary | null { return (item.structured?.summary as AiAnalysisSummary | undefined) || messageRun(item)?.result?.summary || null; }
function messageEvidence(item: AiMessage) { return messageRun(item)?.result?.evidence || {}; }
function messageSearchTaskId(item: AiMessage) { return Number(item.structured?.search_task_id || messageRun(item)?.search_task_id || 0) || null; }
function citationUrl(key: string) { const documentId = Number(key.split(":")[1]); return documentId ? `/api/ai/knowledge/documents/${documentId}/file` : "/ai-knowledge"; }
function toolLabel(tool: string) { return String(toolCatalog.value.find((item) => item.name === tool)?.label || tool); }
function stepDescription(step: AiAnalysisStep) { if (step.tool === "retrieve_knowledge") return "按当前知识来源权限召回引用"; if (step.tool === "build_evidence_report") return "使用后端证据生成中文报告"; if (step.tool === "get_dataset_profile") return step.dataset_name || String(step.dataset_reference || "待选择数据集"); return `${step.dataset_name || "待选择数据集"} · Cell #${step.query_cell_index ?? "-"} · Top ${step.top_k || 10}`; }

function syncPlan(run: AiRun | null) {
  if (!run?.plan) return;
  const analysis = Array.isArray((run.plan as AiAnalysisPlan).steps) ? run.plan as AiAnalysisPlan : null;
  const primary = analysis?.steps.find((step) => step.tool.startsWith("run_"));
  const source = primary || run.plan;
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
  cellTypes.value = run.plan.cell_type_options || [];
}
async function loadModels() {
  const data = await api.aiModels(); models.value = data.models; modelsDisabled.value = data.disabled;
  const saved = Number(localStorage.getItem("ai-model-config"));
  modelConfigId.value = models.value.find((item) => item.id === saved)?.id || models.value.find((item) => item.is_default)?.id || models.value[0]?.id;
}
async function loadConversations() { conversations.value = (await api.aiConversations("analysis")).conversations; }
async function refreshConversation() {
  if (!conversationId.value) return;
  const detail = (await api.aiConversation(conversationId.value)).conversation;
  messages.value = detail.messages || []; runs.value = detail.runs || [];
  currentRun.value = runs.value[runs.value.length - 1] || null; syncPlan(currentRun.value);
  await scrollToEnd();
}
async function openConversation(id: number) {
  stopRealtime(); conversationId.value = id; await refreshConversation();
  if (currentRun.value?.poll_after_ms) startRealtime(currentRun.value);
}
function newConversation() { stopRealtime(); conversationId.value = undefined; messages.value = []; runs.value = []; currentRun.value = null; prompt.value = ""; }
async function deleteConversation() { if (!conversationId.value) return; await api.deleteAiConversation(conversationId.value); message.success("AI 会话已删除"); newConversation(); await loadConversations(); }
async function ensureConversation() { if (conversationId.value) return conversationId.value; const data = await api.createAiConversation(); conversationId.value = data.conversation.id; await loadConversations(); return conversationId.value; }
async function send() {
  if (!prompt.value.trim() || !modelConfigId.value) return;
  sending.value = true;
  try {
    const id = await ensureConversation(); const content = prompt.value.trim();
    const data = await api.sendAiMessage(id, content, modelConfigId.value, knowledgeScopes.value);
    messages.value.push({ id: Date.now(), role: "user", content, structured: null, created_at: new Date().toISOString() });
    prompt.value = ""; currentRun.value = data.run; runs.value.push(data.run); startRealtime(data.run); await loadConversations(); await scrollToEnd();
  } catch (error) { message.error((error as Error).message); } finally { sending.value = false; }
}
function stopPolling() { if (pollTimer) window.clearTimeout(pollTimer); pollTimer = undefined; }
function stopStream() { eventSource?.close(); eventSource = undefined; streamErrors = 0; }
function stopRealtime() { stopPolling(); stopStream(); streamingEnhancement.value = ""; }
function startRealtime(run: AiRun) {
  stopRealtime();
  if (!("EventSource" in window) || !run.stream_url) return pollRun(run.id);
  eventSource = new EventSource(run.stream_url);
  const parse = (event: MessageEvent) => { try { return JSON.parse(event.data || "{}"); } catch { return {}; } };
  eventSource.addEventListener("run.stage", (event) => {
    const payload = parse(event as MessageEvent);
    const next = reduceAiStreamEvent({ enhancement: streamingEnhancement.value, terminal: false, refresh: false, stageMessage: currentRun.value?.stage?.message || null }, "run.stage", payload);
    if (currentRun.value) currentRun.value.stage = { key: payload.key, label: payload.label, message: next.stageMessage, state: payload.state, started_at: null, completed_at: null };
  });
  eventSource.addEventListener("answer.delta", (event) => { streamingEnhancement.value = reduceAiStreamEvent({ enhancement: streamingEnhancement.value, terminal: false, refresh: false, stageMessage: null }, "answer.delta", parse(event as MessageEvent)).enhancement; void scrollToEnd(); });
  for (const name of ["plan.ready", "answer.replace"]) eventSource.addEventListener(name, () => { streamingEnhancement.value = ""; void refreshConversation(); });
  eventSource.addEventListener("answer.completed", () => { streamingEnhancement.value = ""; stopStream(); void refreshConversation(); });
  eventSource.addEventListener("run.completed", () => { stopStream(); void refreshConversation(); });
  eventSource.addEventListener("error", (event) => { const payload = parse(event as MessageEvent); if (payload.message) message.error(payload.message); });
  eventSource.onerror = () => { streamErrors += 1; if (streamErrors >= 3) { stopStream(); pollRun(run.id); } };
}
function pollRun(id: number) {
  stopPolling();
  const tick = async () => {
    try {
      const data = await api.aiRun(id); currentRun.value = data.run; syncPlan(data.run);
      const index = runs.value.findIndex((item) => item.id === data.run.id); if (index >= 0) runs.value[index] = data.run;
      if (["success", "error", "rejected", "needs_input", "awaiting_confirmation"].includes(data.run.status)) await refreshConversation();
      if (data.run.poll_after_ms) pollTimer = window.setTimeout(tick, data.run.poll_after_ms); else stopPolling();
    } catch (error) { stopPolling(); message.error((error as Error).message); }
  };
  void tick();
}
async function onPlanDatasetChange() { planForm.index_id = planIndexOptions.value[0]?.value; cellTypes.value = planForm.dataset_id ? (await api.cellTypes(planForm.dataset_id)).cell_types : []; planForm.filter_cell_type = undefined; }
async function savePlan() {
  if (!currentRun.value) return null; planSaving.value = true;
  try {
    let payload: Record<string, unknown>;
    if (isAnalysisPlan.value) {
      const plan = currentRun.value.plan as AiAnalysisPlan;
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
    currentRun.value = data.run; syncPlan(data.run); if (!data.valid) message.warning("计划仍有需要修正的参数"); else message.success("计划校验通过"); return data.run;
  } catch (error) { message.error((error as Error).message); return null; } finally { planSaving.value = false; }
}
async function approve() { if (!currentRun.value) return; approving.value = true; try { const saved = await savePlan(); if (!saved || saved.status !== "awaiting_confirmation") return; const data = await api.approveAiRun(saved.id); currentRun.value = data.run; startRealtime(data.run); } catch (error) { message.error((error as Error).message); } finally { approving.value = false; } }
async function reject() { if (!currentRun.value) return; currentRun.value = (await api.rejectAiRun(currentRun.value.id)).run; await refreshConversation(); }
async function cancelRun() { if (!currentRun.value) return; try { currentRun.value = (await api.cancelAiRun(currentRun.value.id)).run; message.info("已请求停止后续分析"); if (!currentRun.value.can_cancel) stopRealtime(); } catch (error) { message.error((error as Error).message); } }
function openQueryLab(taskId: number | null) { if (taskId) router.push({ path: "/query-lab", query: { history_id: taskId } }); }
async function scrollToEnd() { await nextTick(); if (messageStream.value) messageStream.value.scrollTop = messageStream.value.scrollHeight; }

watch(modelConfigId, (value) => { if (value) localStorage.setItem("ai-model-config", String(value)); });
watch(() => messages.value.length, () => { void scrollToEnd(); });
onMounted(async () => { try { const [, , , jointData, capabilityData] = await Promise.all([loadModels(), loadConversations(), datasetsStore.loadAll(), api.jointIndexes(), api.aiCapabilities()]); jointIndexes.value = jointData.joint_indexes; toolCatalog.value = capabilityData.tools; const requested = Number(route.query.conversation_id); const initial = conversations.value.find((item) => item.id === requested) || conversations.value[0]; if (initial) await openConversation(initial.id); if (typeof route.query.prompt === "string" && route.query.prompt.trim()) prompt.value = route.query.prompt.slice(0, 4000); } catch (error) { message.error((error as Error).message); } });
watch(() => route.query.conversation_id, (value) => { const id = Number(value); if (id && id !== conversationId.value) void openConversation(id); });
onBeforeUnmount(stopRealtime);
</script>

<style scoped>
.ai-alert { margin-bottom: 16px; }
.ai-workbench { display: grid; grid-template-columns: 250px minmax(0, 1fr); gap: 18px; align-items: start; }
.ai-history { padding: 14px; position: sticky; top: 82px; }
.history-head, .run-head, .plan-head, .answer-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.history-head { margin-bottom: 10px; }
.history-list { display: grid; gap: 6px; margin-bottom: 14px; max-height: 520px; overflow-y: auto; }
.history-item { border: 1px solid transparent; border-radius: 8px; background: #f8fafc; padding: 10px; text-align: left; cursor: pointer; }
.history-item.active { border-color: #91caff; background: #e6f4ff; }
.history-item span, .history-item small { display: block; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.history-item small { color: #64748b; margin-top: 3px; }
.conversation-panel { overflow: hidden; }
.message-stream { min-height: 430px; max-height: calc(100vh - 330px); overflow-y: auto; padding: 18px; background: #f8fafc; }
.empty-prompt { min-height: 260px; display: flex; align-items: center; justify-content: center; flex-direction: column; gap: 10px; color: #64748b; text-align: center; }
.empty-icon { font-size: 34px; color: #1677ff; }
.message-row { display: flex; margin-bottom: 12px; }
.message-row.user { justify-content: flex-end; }
.message-bubble { max-width: 82%; padding: 10px 13px; border-radius: 10px; background: #fff; border: 1px solid #e2e8f0; }
.message-row.user .message-bubble { background: #e6f4ff; border-color: #91caff; }
.message-bubble small { color: #64748b; display: block; margin-bottom: 4px; }
.result-bubble { width: min(760px, 88%); }
.result-bubble p { margin: 10px 0; white-space: pre-line; }
.plain-message { white-space: pre-line; }
.finding { padding: 8px 0; border-top: 1px solid #eef2f7; }
.evidence-tags { margin-top: 6px; display: flex; flex-wrap: wrap; gap: 5px; }
.citation-list { display: grid; gap: 7px; margin-top: 12px; padding-top: 10px; border-top: 1px solid #e2e8f0; }
.citation-item { display: block; border: 1px solid #dbeafe; background: #eff6ff; border-radius: 7px; padding: 7px 9px; }
.citation-item small { display: block; color: #64748b; margin-top: 3px; }
.run-card, .plan-card { margin: 12px 0; padding: 14px; border: 1px solid #d9e3f0; border-radius: 10px; background: #fff; }
.run-card :deep(.ant-steps) { margin: 18px 0 10px; }
.stage-alert { margin-top: 12px; }
.summary-status { margin-top: 8px; color: #64748b; font-size: 13px; }
.streaming-answer { margin-top: 10px; border: 1px solid #d8b4fe; background: #faf5ff; padding: 10px; border-radius: 8px; }
.streaming-answer p { white-space: pre-line; margin: 7px 0 0; }
.streaming-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #9333ea; margin-right: 7px; animation: pulse 1.2s infinite; }
.analysis-steps { display: grid; gap: 7px; margin-bottom: 14px; }
.analysis-step { display: grid; grid-template-columns: auto 180px minmax(0, 1fr); gap: 8px; align-items: center; padding: 8px; border: 1px solid #e2e8f0; border-radius: 8px; }
.plan-head { margin-bottom: 12px; }
.plan-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 16px; }
.composer { padding: 16px; border-top: 1px solid #e2e8f0; }
.composer-actions { display: flex; align-items: center; justify-content: space-between; margin-top: 10px; }
.knowledge-scopes { display: flex; gap: 12px; align-items: center; margin-top: 10px; flex-wrap: wrap; }
@keyframes pulse { 50% { opacity: .35; transform: scale(.8); } }
@media (max-width: 900px) { .ai-workbench { grid-template-columns: 1fr; } .ai-history { position: static; } .message-stream { max-height: none; } }
@media (max-width: 650px) { .plan-grid { grid-template-columns: 1fr; } .analysis-step { grid-template-columns: auto 1fr; } .analysis-step span { grid-column: 1 / -1; } .message-bubble, .result-bubble { max-width: 94%; width: auto; } }
</style>
