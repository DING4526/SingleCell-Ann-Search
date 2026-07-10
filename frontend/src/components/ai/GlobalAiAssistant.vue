<template>
  <div :class="['global-assistant', { workspace: embedded }]">
    <aside v-if="embedded" class="assistant-history">
      <div class="history-head"><strong>助手会话</strong><a-button size="small" @click="newConversation">新建</a-button></div>
      <a-list size="small" :data-source="conversations" :loading="loading">
        <template #renderItem="{ item }">
          <a-list-item :class="{ active: item.id === conversationId }" @click="openConversation(item.id)">
            <a-list-item-meta :title="item.title" />
          </a-list-item>
        </template>
      </a-list>
    </aside>

    <section class="assistant-main">
      <header class="assistant-head">
        <div><strong>全局 AI 助手</strong><small>理解当前页面，帮助导航和调用平台功能</small></div>
        <div class="head-actions">
          <a-select v-model:value="modelId" size="small" style="min-width:150px" :options="modelOptions" />
          <a-button v-if="!embedded" size="small" @click="$router.push('/ai-assistant')">完整工作台</a-button>
          <a-button v-else size="small" @click="newConversation">新建会话</a-button>
        </div>
      </header>

      <div class="context-strip">
        <a-switch v-model:checked="contextEnabled" size="small" />
        <span>使用页面上下文</span>
        <a-tag v-if="contextEnabled" closable @close.prevent="contextEnabled = false">{{ contextLabel }}</a-tag>
      </div>

      <div ref="messagePane" class="assistant-messages">
        <a-empty v-if="!messages.length" description="可以问：这个页面能做什么？或“打开当前数据集的检索实验室”" />
        <article v-for="item in messages" :key="item.id" :class="['assistant-message', item.role]">
          <small>{{ item.role === 'user' ? '你' : 'AI 助手' }}</small>
          <div class="message-content">{{ item.content }}</div>
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
            {{ clientAction(item)?.target === 'ai_analysis' ? '转到 AI Analysis' : '打开相关页面' }}
          </a-button>
          <div v-if="item.citations?.length" class="assistant-citations">
            <a-tag v-for="citation in item.citations" :key="citation.key">{{ citation.source_title }}</a-tag>
          </div>
        </article>
        <a-card v-if="currentRun && !terminal(currentRun)" size="small" class="run-card">
          <a-spin size="small" /> {{ currentRun.stage?.message || 'AI 正在处理…' }}
          <a-button v-if="currentRun.can_cancel" size="small" type="link" danger @click="cancelRun">取消</a-button>
        </a-card>
      </div>

      <footer class="assistant-composer">
        <a-textarea v-model:value="prompt" :rows="embedded ? 3 : 2" :maxlength="4000" placeholder="询问当前页面，或用自然语言打开、预填和调用平台功能" @keydown.ctrl.enter.prevent="send" />
        <div><span class="muted">Ctrl + Enter 发送 · 写操作始终先确认</span><a-button type="primary" :loading="sending" :disabled="!prompt.trim() || !modelId" @click="send">发送</a-button></div>
      </footer>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { message } from "ant-design-vue";
import { api } from "@/services/api";
import type { AiAssistantClientAction, AiConversation, AiMessage, AiModelConfig, AiRun } from "@/types";

defineProps<{ embedded?: boolean }>();

const route = useRoute();
const router = useRouter();
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
const currentRun = ref<AiRun | null>(null);
const messagePane = ref<HTMLElement>();
let source: EventSource | null = null;
let pollTimer: number | null = null;

const modelOptions = computed(() => models.value.map((item) => ({ value: item.id, label: item.display_name })));
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
function assistantAction(item: AiMessage) { return item.structured?.action as Record<string, unknown> | undefined; }
function clientAction(item: AiMessage) { return item.structured?.client_action as AiAssistantClientAction | undefined; }
function toolStatus(id: number) { return runs.value.flatMap((run) => run.tool_calls || []).find((tool) => tool.id === id)?.status || "proposed"; }
function displayValue(value: unknown) { return typeof value === "object" ? JSON.stringify(value) : String(value ?? "-"); }
function actionName(value: unknown) { return ({ submit_dataset_processing: "处理数据集", submit_index_build: "构建索引", submit_index_experiment: "运行索引实验", submit_index_evaluation: "评估索引", submit_joint_index_build: "构建联合索引", reindex_knowledge_document: "重建知识索引", create_personal_knowledge_note: "创建个人知识笔记" } as Record<string, string>)[String(value)] || String(value || "平台操作"); }

async function loadBase() {
  loading.value = true;
  try {
    const [modelData, conversationData] = await Promise.all([api.aiModels(), api.aiConversations("assistant")]);
    models.value = modelData.models;
    modelId.value ||= models.value.find((item) => item.is_default)?.id || models.value[0]?.id;
    conversations.value = conversationData.conversations;
    const requested = Number(route.query.conversation_id);
    const initial = conversations.value.find((item) => item.id === requested) || conversations.value[0];
    if (initial && initial.id !== conversationId.value) await openConversation(initial.id);
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
  messages.value = detail.messages || [];
  runs.value = detail.runs || [];
  currentRun.value = [...runs.value].reverse().find((item) => !terminal(item)) || runs.value[runs.value.length - 1] || null;
  if (currentRun.value && !terminal(currentRun.value)) startRealtime(currentRun.value);
  await scrollEnd();
}

function newConversation() {
  stopRealtime(); conversationId.value = undefined; messages.value = []; runs.value = []; currentRun.value = null; prompt.value = "";
}

async function refreshConversation() {
  if (!conversationId.value) return;
  const detail = (await api.aiConversation(conversationId.value)).conversation;
  messages.value = detail.messages || [];
  runs.value = detail.runs || [];
  const latest = runs.value[runs.value.length - 1];
  if (latest) currentRun.value = latest;
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

function startRealtime(run: AiRun) {
  stopRealtime();
  if (typeof EventSource !== "undefined") {
    source = new EventSource(run.stream_url);
    const refreshEvents = ["answer.replace", "answer.completed", "action.proposed", "action.status", "run.completed", "error"];
    refreshEvents.forEach((name) => source?.addEventListener(name, async (event) => {
      const payload = JSON.parse((event as MessageEvent).data || "{}");
      if (name === "run.completed" || name === "error") stopRealtime();
      await refreshConversation();
      if ((name === "ui.navigate" || name === "assistant.handoff") && payload.auto) await navigate(payload);
    }));
    ["ui.navigate", "assistant.handoff"].forEach((name) => source?.addEventListener(name, async (event) => {
      const payload = JSON.parse((event as MessageEvent).data || "{}"); if (payload.auto) await navigate(payload);
    }));
    source.onerror = () => { source?.close(); source = null; startPolling(run.id); };
  } else startPolling(run.id);
}

function startPolling(runId: number) {
  pollTimer = window.setInterval(async () => {
    const run = (await api.aiRun(runId)).run; currentRun.value = run; await refreshConversation();
    if (terminal(run)) stopRealtime();
  }, 1200);
}
function stopRealtime() { source?.close(); source = null; if (pollTimer !== null) window.clearInterval(pollTimer); pollTimer = null; }

async function navigate(action: AiAssistantClientAction) {
  if (!action.path.startsWith("/")) return message.error("助手返回了无效页面地址");
  await router.push(action.path);
}
async function approveAction(id: number) { if (!id) return; actionLoading.value = true; try { await api.approveAiToolCall(id); message.success("平台任务已提交"); await refreshConversation(); } catch (error) { message.error((error as Error).message); } finally { actionLoading.value = false; } }
async function rejectAction(id: number) { if (!id) return; actionLoading.value = true; try { await api.rejectAiToolCall(id); message.info("操作已拒绝"); await refreshConversation(); } catch (error) { message.error((error as Error).message); } finally { actionLoading.value = false; } }
async function cancelRun() { if (!currentRun.value) return; await api.cancelAiRun(currentRun.value.id); await refreshConversation(); }
async function scrollEnd() { await nextTick(); if (messagePane.value) messagePane.value.scrollTop = messagePane.value.scrollHeight; }

watch(() => route.fullPath, () => { /* computed context updates without retaining form secrets */ });
onMounted(loadBase);
onBeforeUnmount(stopRealtime);
</script>

<style scoped>
.global-assistant { height: 100%; display: flex; min-height: 0; background: #f8fafc; }
.global-assistant.workspace { min-height: calc(100vh - 150px); border: 1px solid #e2e8f0; border-radius: 12px; overflow: hidden; }
.assistant-history { width: 250px; background: white; border-right: 1px solid #e2e8f0; overflow: auto; }
.history-head, .assistant-head, .context-strip, .assistant-composer > div { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
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
.assistant-message small { color: #64748b; display: block; margin-bottom: 4px; }
.message-content { line-height: 1.65; }
.action-card { margin-top: 12px; white-space: normal; }
.action-buttons { display: flex; gap: 8px; margin-top: 12px; }
.assistant-citations { margin-top: 8px; }
.run-card { margin-top: 8px; }
.assistant-composer { padding: 12px 14px; background: white; border-top: 1px solid #e2e8f0; }
.assistant-composer > div { margin-top: 8px; }
.muted { color: #94a3b8; font-size: 12px; }
@media (max-width: 800px) { .assistant-history { display: none; } .head-actions :deep(.ant-select) { display: none; } }
</style>
