<template>
  <div class="ai-admin-stack">
    <a-alert
      :type="credentialStore.ready ? 'success' : 'warning'"
      show-icon
      :message="credentialStore.message"
      :description="credentialStore.ready ? 'API Key 加密保存且永不返回明文。' : '请先在服务器设置 AI_CREDENTIAL_ENCRYPTION_KEY。'"
    />

    <div class="ai-section">
      <div class="section-head">
        <div><strong>系统策略</strong><div class="muted">控制全局开关、共享额度和输入限制。</div></div>
        <a-button type="primary" :loading="savingSettings" @click="saveSettings">保存策略</a-button>
      </div>
      <a-form v-if="settings" layout="inline" class="settings-form">
        <a-form-item label="AI 功能"><a-switch v-model:checked="settings.enabled" /></a-form-item>
        <a-form-item label="每日限额"><a-input-number v-model:value="settings.daily_request_limit" :min="0" :max="100000" /></a-form-item>
        <a-form-item label="并发 Run"><a-input-number v-model:value="settings.max_concurrent_runs" :min="1" :max="10" /></a-form-item>
        <a-form-item label="输入字符"><a-input-number v-model:value="settings.max_prompt_chars" :min="100" :max="50000" /></a-form-item>
        <a-form-item label="RAG"><a-switch v-model:checked="settings.rag_enabled" /></a-form-item>
        <a-form-item label="召回片段"><a-input-number v-model:value="settings.default_knowledge_top_k" :min="1" :max="8" /></a-form-item>
        <a-form-item label="单文件 MB"><a-input-number v-model:value="settings.max_knowledge_file_mb" :min="1" :max="100" /></a-form-item>
        <a-form-item><a-button @click="$router.push('/ai-knowledge')">管理平台知识</a-button></a-form-item>
      </a-form>
    </div>

    <div class="ai-section">
      <div class="section-head">
        <div><strong>供应商凭据</strong><div class="muted">一个凭据可以挂载多个可选模型。</div></div>
        <a-button type="primary" :disabled="!credentialStore.ready" @click="openProvider()">添加供应商</a-button>
      </div>
      <a-table :data-source="providers" :columns="providerColumns" row-key="id" size="small" :loading="loading">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'provider'">
            <a-tag>{{ providerLabel(record.provider) }}</a-tag> {{ record.name }}
          </template>
          <template v-else-if="column.key === 'secret'">{{ record.api_key_hint }}</template>
          <template v-else-if="column.key === 'status'">
            <a-tag :color="testColor(record.last_test_status)">{{ testLabel(record.last_test_status) }}</a-tag>
            <a-tag :color="record.enabled ? 'green' : 'default'">{{ record.enabled ? '启用' : '停用' }}</a-tag>
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-space>
              <a-button size="small" @click="openProvider(record)">编辑/换 Key</a-button>
              <a-popconfirm title="确认删除未使用的供应商配置？" @confirm="removeProvider(record.id)"><a-button size="small" danger>删除</a-button></a-popconfirm>
            </a-space>
          </template>
        </template>
      </a-table>
    </div>

    <div class="ai-section">
      <div class="section-head">
        <div><strong>可用模型</strong><div class="muted">模型连接测试成功后才能向用户启用。</div></div>
        <a-button type="primary" :disabled="!providers.length" @click="openModel()">添加模型</a-button>
      </div>
      <a-table :data-source="models" :columns="modelColumns" row-key="id" size="small" :loading="loading">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'model'">
            <strong>{{ record.display_name }}</strong>
            <a-tag :color="record.capability === 'embedding' ? 'purple' : 'blue'">{{ record.capability === 'embedding' ? 'Embedding' : 'Chat' }}</a-tag>
            <div class="muted">{{ record.model_id }}<template v-if="record.embedding_dimensions"> · {{ record.embedding_dimensions }} 维</template></div>
          </template>
          <template v-else-if="column.key === 'status'">
            <a-tag :color="testColor(record.last_test_status)">{{ testLabel(record.last_test_status) }}</a-tag>
            <a-tag v-if="record.is_default" color="blue">默认</a-tag>
          </template>
          <template v-else-if="column.key === 'enabled'">
            <a-switch :checked="record.enabled" :disabled="record.last_test_status !== 'success'" @change="setModelEnabled(record, Boolean($event))" />
          </template>
          <template v-else-if="column.key === 'actions'">
            <a-space wrap>
              <a-button size="small" :loading="testingModelId === record.id" @click="testModel(record.id)">测试</a-button>
              <a-button size="small" @click="openModel(record)">编辑</a-button>
              <a-button v-if="record.enabled && !record.is_default" size="small" @click="makeDefault(record.id)">设为默认</a-button>
              <a-popconfirm title="确认删除未使用的模型？" @confirm="removeModel(record.id)"><a-button size="small" danger>删除</a-button></a-popconfirm>
            </a-space>
          </template>
        </template>
      </a-table>
    </div>

    <div class="ai-section">
      <div class="section-head"><div><strong>聚合用量</strong><div class="muted">仅显示计数和 Token，不读取用户会话正文。</div></div><a-button @click="loadUsage">刷新</a-button></div>
      <a-row v-if="usage" :gutter="16">
        <a-col :xs="12" :md="6"><a-statistic title="AI Runs" :value="usage.totals.runs" /></a-col>
        <a-col :xs="12" :md="6"><a-statistic title="供应商请求" :value="usage.totals.provider_requests" /></a-col>
        <a-col :xs="12" :md="6"><a-statistic title="输入 Token" :value="usage.totals.input_tokens" /></a-col>
        <a-col :xs="12" :md="6"><a-statistic title="输出 Token" :value="usage.totals.output_tokens" /></a-col>
        <a-col :xs="12" :md="6"><a-statistic title="Embedding 请求" :value="usage.totals.embedding_requests" /></a-col>
      </a-row>
    </div>
  </div>

  <a-modal v-model:open="providerOpen" :title="providerForm.id ? '编辑供应商' : '添加供应商'" ok-text="保存" :confirm-loading="modalLoading" @ok="saveProvider">
    <a-form layout="vertical">
      <a-form-item label="供应商">
        <a-select v-model:value="providerForm.provider" :disabled="Boolean(providerForm.id)" @change="applyProviderPreset">
          <a-select-option v-for="item in catalog" :key="item.key" :value="item.key">{{ item.label }}</a-select-option>
        </a-select>
      </a-form-item>
      <a-form-item label="显示名称"><a-input v-model:value="providerForm.name" /></a-form-item>
      <a-form-item label="Base URL"><a-input v-model:value="providerForm.base_url" /></a-form-item>
      <a-form-item :label="providerForm.id ? '替换 API Key（留空则保留）' : 'API Key'">
        <a-input-password v-model:value="providerForm.api_key" autocomplete="new-password" />
      </a-form-item>
      <a-form-item label="超时（秒）"><a-input-number v-model:value="providerForm.timeout_seconds" :min="15" :max="600" style="width:100%" /></a-form-item>
      <a-form-item label="供应商启用"><a-switch v-model:checked="providerForm.enabled" /></a-form-item>
    </a-form>
  </a-modal>

  <a-modal v-model:open="modelOpen" :title="modelForm.id ? '编辑模型' : '添加模型'" ok-text="保存" :confirm-loading="modalLoading" @ok="saveModel">
    <a-form layout="vertical">
      <a-form-item label="供应商凭据">
        <a-select v-model:value="modelForm.provider_config_id" :disabled="Boolean(modelForm.id)">
          <a-select-option v-for="item in providers" :key="item.id" :value="item.id">{{ item.name }} · {{ providerLabel(item.provider) }}</a-select-option>
        </a-select>
      </a-form-item>
      <a-form-item label="模型能力">
        <a-segmented v-model:value="modelForm.capability" :disabled="Boolean(modelForm.id)" :options="[{ value: 'chat', label: '对话模型' }, { value: 'embedding', label: 'Embedding' }]" />
      </a-form-item>
      <a-form-item label="模型 ID">
        <a-auto-complete v-model:value="modelForm.model_id" :options="modelSuggestions" placeholder="选择建议项或输入供应商控制台中的模型 ID" />
      </a-form-item>
      <a-form-item label="显示名称"><a-input v-model:value="modelForm.display_name" /></a-form-item>
      <a-alert v-if="modelForm.id" type="info" show-icon message="修改模型 ID 后需要重新测试才能启用。" />
    </a-form>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { message } from "ant-design-vue";
import { api } from "@/services/api";
import type { AiModelConfig, AiProviderCatalogItem, AiProviderConfig, AiSettings, AiUsage } from "@/types";

const loading = ref(false);
const modalLoading = ref(false);
const savingSettings = ref(false);
const testingModelId = ref<number | null>(null);
const settings = ref<AiSettings | null>(null);
const credentialStore = reactive({ ready: false, message: "正在检查凭据存储..." });
const catalog = ref<AiProviderCatalogItem[]>([]);
const providers = ref<AiProviderConfig[]>([]);
const models = ref<AiModelConfig[]>([]);
const usage = ref<AiUsage | null>(null);
const providerOpen = ref(false);
const modelOpen = ref(false);
const providerForm = reactive({ id: 0, provider: "openai", name: "", base_url: "", api_key: "", timeout_seconds: 180, enabled: true });
const modelForm = reactive<{ id: number; provider_config_id: number; model_id: string; display_name: string; capability: "chat" | "embedding" }>({ id: 0, provider_config_id: 0, model_id: "", display_name: "", capability: "chat" });

const providerColumns = [
  { title: "供应商", key: "provider", width: 220 }, { title: "Base URL", dataIndex: "base_url" },
  { title: "密钥", key: "secret", width: 140 }, { title: "状态", key: "status", width: 170 },
  { title: "操作", key: "actions", width: 220 },
];
const modelColumns = [
  { title: "模型", key: "model" }, { title: "供应商", dataIndex: "provider_name", width: 170 },
  { title: "测试状态", key: "status", width: 150 }, { title: "向用户启用", key: "enabled", width: 110 },
  { title: "操作", key: "actions", width: 300 },
];

const selectedProviderType = computed(() => providers.value.find((item) => item.id === modelForm.provider_config_id)?.provider);
const modelSuggestions = computed(() => {
  const item = catalog.value.find((entry) => entry.key === selectedProviderType.value);
  const values = modelForm.capability === "embedding" ? item?.suggested_embedding_models : item?.suggested_models;
  return (values || []).map((value) => ({ value }));
});

function providerLabel(key: string) { return catalog.value.find((item) => item.key === key)?.label || key; }
function testLabel(status: string) { return ({ success: "测试成功", error: "测试失败", untested: "未测试" } as Record<string, string>)[status] || status; }
function testColor(status: string) { return ({ success: "green", error: "red", untested: "default" } as Record<string, string>)[status] || "default"; }

async function loadAll() {
  loading.value = true;
  try {
    const [settingData, providerData, modelData] = await Promise.all([api.aiAdminSettings(), api.aiAdminProviders(), api.aiAdminModels()]);
    settings.value = settingData.settings;
    Object.assign(credentialStore, settingData.credential_store);
    catalog.value = settingData.catalog;
    providers.value = providerData.providers;
    models.value = modelData.models;
    await loadUsage();
  } catch (error) { message.error((error as Error).message); }
  finally { loading.value = false; }
}
async function loadUsage() { try { usage.value = (await api.aiAdminUsage()).usage; } catch (error) { message.error((error as Error).message); } }
async function saveSettings() {
  if (!settings.value) return;
  savingSettings.value = true;
  try { settings.value = (await api.updateAiAdminSettings(settings.value)).settings; message.success("AI 策略已保存"); }
  catch (error) { message.error((error as Error).message); }
  finally { savingSettings.value = false; }
}
function applyProviderPreset() {
  const preset = catalog.value.find((item) => item.key === providerForm.provider);
  if (!preset) return;
  providerForm.name = preset.label;
  providerForm.base_url = preset.default_base_url;
}
function openProvider(record?: AiProviderConfig) {
  if (record) Object.assign(providerForm, { id: record.id, provider: record.provider, name: record.name, base_url: record.base_url, api_key: "", timeout_seconds: record.timeout_seconds, enabled: record.enabled });
  else { Object.assign(providerForm, { id: 0, provider: "openai", name: "", base_url: "", api_key: "", timeout_seconds: 180, enabled: true }); applyProviderPreset(); }
  providerOpen.value = true;
}
async function saveProvider() {
  if (!providerForm.name || !providerForm.base_url || (!providerForm.id && !providerForm.api_key)) return message.warning("请完整填写供应商配置");
  modalLoading.value = true;
  try {
    const payload = { provider: providerForm.provider, name: providerForm.name, base_url: providerForm.base_url, api_key: providerForm.api_key, timeout_seconds: providerForm.timeout_seconds, enabled: providerForm.enabled };
    if (providerForm.id) await api.updateAiProvider(providerForm.id, payload); else await api.createAiProvider(payload);
    providerOpen.value = false; message.success("供应商配置已保存"); await loadAll();
  } catch (error) { message.error((error as Error).message); }
  finally { modalLoading.value = false; }
}
async function removeProvider(id: number) { try { await api.deleteAiProvider(id); message.success("供应商已删除"); await loadAll(); } catch (error) { message.error((error as Error).message); } }
function openModel(record?: AiModelConfig) {
  if (record) Object.assign(modelForm, { id: record.id, provider_config_id: record.provider_config_id || 0, model_id: record.model_id, display_name: record.display_name, capability: record.capability || "chat" });
  else Object.assign(modelForm, { id: 0, provider_config_id: providers.value[0]?.id || 0, model_id: "", display_name: "", capability: "chat" });
  modelOpen.value = true;
}
async function saveModel() {
  if (!modelForm.provider_config_id || !modelForm.model_id) return message.warning("请选择供应商并填写模型 ID");
  modalLoading.value = true;
  try {
    const payload = { provider_config_id: modelForm.provider_config_id, model_id: modelForm.model_id, display_name: modelForm.display_name || modelForm.model_id, capability: modelForm.capability };
    if (modelForm.id) await api.updateAiModel(modelForm.id, payload); else await api.createAiModel(payload);
    modelOpen.value = false; message.success("模型配置已保存"); await loadAll();
  } catch (error) { message.error((error as Error).message); }
  finally { modalLoading.value = false; }
}
async function testModel(id: number) {
  testingModelId.value = id;
  try { const data = await api.testAiModel(id); message.success(`连接成功，耗时 ${Math.round(data.latency_ms)} ms`); }
  catch (error) { message.error((error as Error).message); }
  finally { testingModelId.value = null; await loadAll(); }
}
async function setModelEnabled(record: AiModelConfig, enabled: boolean) { try { await api.updateAiModel(record.id, { enabled }); await loadAll(); } catch (error) { message.error((error as Error).message); } }
async function makeDefault(id: number) { try { await api.updateAiModel(id, { is_default: true }); message.success("默认模型已更新"); await loadAll(); } catch (error) { message.error((error as Error).message); } }
async function removeModel(id: number) { try { await api.deleteAiModel(id); message.success("模型已删除"); await loadAll(); } catch (error) { message.error((error as Error).message); } }

onMounted(loadAll);
</script>

<style scoped>
.ai-admin-stack { display: grid; gap: 18px; padding: 18px 0; }
.ai-section { padding: 16px; border: 1px solid #e2e8f0; border-radius: 10px; background: #fff; }
.section-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 14px; }
.settings-form { gap: 12px 0; }
@media (max-width: 720px) { .section-head { align-items: flex-start; flex-direction: column; } }
</style>
