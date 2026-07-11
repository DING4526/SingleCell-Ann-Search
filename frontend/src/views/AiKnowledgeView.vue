<template>
  <PageHeader title="AI 知识库" description="维护平台、数据集和个人资料；关键词检索始终可用，语义索引可按模型配置增强。">
    <template #actions><a-space><a-button v-if="auth.isAdmin" @click="syncBuiltin">检查内置知识更新</a-button><a-button @click="loadDocuments">刷新状态</a-button></a-space></template>
  </PageHeader>

  <a-alert class="knowledge-note" type="info" show-icon
    message="资料只在当前权限范围内召回"
    description="平台资料由管理员维护；数据集资料沿用数据集权限；个人资料仅自己可见。知识内容不会获得工具调用权限。" />

  <div class="knowledge-grid">
    <section class="surface upload-card">
      <h3>上传资料</h3>
      <a-form layout="vertical">
        <a-form-item label="知识空间">
          <a-select v-model:value="form.scope" :options="scopeOptions" />
        </a-form-item>
        <a-form-item v-if="form.scope === 'dataset'" label="关联数据集">
          <a-select v-model:value="form.dataset_id" :options="editableDatasetOptions" placeholder="选择有 Editor 权限的数据集" />
        </a-form-item>
        <a-form-item label="标题"><a-input v-model:value="form.title" placeholder="默认使用文件名" /></a-form-item>
        <a-form-item label="说明"><a-textarea v-model:value="form.description" :rows="2" /></a-form-item>
        <a-form-item label="PDF / Markdown / TXT">
          <input ref="fileInput" type="file" accept=".pdf,.md,.markdown,.txt" @change="onFileChange" />
          <div v-if="selectedFile" class="selected-file">{{ selectedFile.name }} · {{ formatBytes(selectedFile.size) }}</div>
        </a-form-item>
        <a-button type="primary" block :loading="uploading" :disabled="!selectedFile || (form.scope === 'dataset' && !form.dataset_id)" @click="upload">
          上传并建立索引
        </a-button>
      </a-form>

      <a-divider />
      <h3>检索预览</h3>
      <a-input-search v-model:value="previewQuery" :loading="previewing" placeholder="检查当前账号可召回的资料" @search="preview" />
      <a-list v-if="previewHits.length" size="small" :data-source="previewHits" class="preview-list">
        <template #renderItem="{ item }">
          <a-list-item>
            <a-list-item-meta :title="`${item.title}${item.page_number ? ` · 第 ${item.page_number} 页` : ''}`" :description="item.excerpt" />
          </a-list-item>
        </template>
      </a-list>
    </section>

    <section class="surface library-card">
      <div class="library-head">
        <h3>可访问资料</h3>
        <a-segmented v-model:value="scopeFilter" :options="filterOptions" />
      </div>
      <a-empty v-if="!loading && !filteredDocuments.length" description="当前空间暂无资料" />
      <a-list :loading="loading" :data-source="filteredDocuments">
        <template #renderItem="{ item }">
          <a-list-item>
            <template #actions>
              <a :href="`/api/ai/knowledge/documents/${item.id}/file`">原文</a>
              <a v-if="item.can_manage" @click="reindex(item.id)">重建</a>
              <a-popconfirm v-if="item.can_manage" title="删除后将停止召回该资料，确定继续？" @confirm="remove(item.id)">
                <a class="danger-link">删除</a>
              </a-popconfirm>
            </template>
            <a-list-item-meta :title="item.title" :description="item.description || item.original_filename || '内置平台知识'">
              <template #avatar><FileTextOutlined class="document-icon" /></template>
            </a-list-item-meta>
            <div class="document-meta">
              <a-tag :color="scopeColor(item.scope)">{{ scopeLabel(item.scope) }}</a-tag>
              <a-tag :color="statusColor(item.status)">{{ statusLabel(item.status) }}</a-tag>
              <a-tag :color="item.semantic_status === 'ready' ? 'purple' : 'default'">
                {{ item.semantic_status === 'ready' ? '语义索引' : '关键词索引' }}
              </a-tag>
              <span>{{ item.chunk_count }} 片段</span>
              <span v-if="item.page_count">{{ item.page_count }} 页</span>
              <span>{{ formatBytes(item.size_bytes) }}</span>
            </div>
            <a-alert v-if="item.error_message" type="warning" :message="item.error_message" show-icon />
          </a-list-item>
        </template>
      </a-list>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { FileTextOutlined } from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import PageHeader from "@/components/PageHeader.vue";
import { api } from "@/services/api";
import { useAuthStore } from "@/stores/auth";
import { useDatasetStore } from "@/stores/datasets";
import type { KnowledgeDocument, KnowledgeHit } from "@/types";

const auth = useAuthStore();
const datasets = useDatasetStore();
const documents = ref<KnowledgeDocument[]>([]);
const loading = ref(false);
const uploading = ref(false);
const selectedFile = ref<File>();
const fileInput = ref<HTMLInputElement>();
const scopeFilter = ref("all");
const previewQuery = ref("");
const previewing = ref(false);
const previewHits = ref<KnowledgeHit[]>([]);
const form = reactive<{ scope: "personal" | "dataset" | "platform"; dataset_id?: number; title: string; description: string }>({ scope: "personal", title: "", description: "" });
let refreshTimer: number | undefined;

const scopeOptions = computed(() => [
  { value: "personal", label: "个人知识（仅自己）" },
  { value: "dataset", label: "数据集知识（沿用数据权限）" },
  ...(auth.isAdmin ? [{ value: "platform", label: "平台知识（所有 AI 用户）" }] : []),
]);
const editableDatasetOptions = computed(() => datasets.datasets.filter((item) => item.can_edit).map((item) => ({ value: item.id, label: item.name })));
const filterOptions = [
  { value: "all", label: "全部" }, { value: "platform", label: "平台" },
  { value: "dataset", label: "数据集" }, { value: "personal", label: "个人" },
];
const filteredDocuments = computed(() => documents.value.filter((item) => scopeFilter.value === "all" || item.scope === scopeFilter.value));

function onFileChange(event: Event) { selectedFile.value = (event.target as HTMLInputElement).files?.[0]; }
function formatBytes(value: number) { if (!value) return "0 B"; if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`; return `${(value / 1024 / 1024).toFixed(1)} MB`; }
function scopeLabel(scope: string) { return ({ platform: "平台", dataset: "数据集", personal: "个人" } as Record<string, string>)[scope] || scope; }
function scopeColor(scope: string) { return ({ platform: "blue", dataset: "cyan", personal: "green" } as Record<string, string>)[scope] || "default"; }
function statusLabel(status: string) { return ({ pending: "等待处理", extracting: "提取文本", indexing: "建立索引", ready: "就绪", degraded: "降级可用", error: "失败" } as Record<string, string>)[status] || status; }
function statusColor(status: string) { if (status === "ready") return "green"; if (status === "degraded") return "orange"; if (status === "error") return "red"; return "blue"; }

async function loadDocuments() {
  loading.value = true;
  try {
    documents.value = (await api.knowledgeDocuments()).documents;
    if (documents.value.some((item) => ["pending", "extracting", "indexing"].includes(item.status))) {
      window.clearTimeout(refreshTimer); refreshTimer = window.setTimeout(loadDocuments, 1800);
    }
  } catch (error) { message.error((error as Error).message); } finally { loading.value = false; }
}
async function upload() {
  if (!selectedFile.value) return;
  uploading.value = true;
  try {
    await api.uploadKnowledgeDocument({ file: selectedFile.value, ...form });
    message.success("资料已上传，正在建立关键词与语义索引");
    selectedFile.value = undefined; if (fileInput.value) fileInput.value.value = "";
    form.title = ""; form.description = ""; await loadDocuments();
  } catch (error) { message.error((error as Error).message); } finally { uploading.value = false; }
}
async function reindex(id: number) { try { await api.reindexKnowledgeDocument(id); message.success("已提交重建"); await loadDocuments(); } catch (error) { message.error((error as Error).message); } }
async function remove(id: number) { try { await api.deleteKnowledgeDocument(id); message.success("资料已删除"); await loadDocuments(); } catch (error) { message.error((error as Error).message); } }
async function syncBuiltin() { try { await api.syncBuiltinKnowledge(); message.success("内置平台知识已同步"); await loadDocuments(); } catch (error) { message.error((error as Error).message); } }
async function preview() { if (!previewQuery.value.trim()) return; previewing.value = true; try { previewHits.value = (await api.previewKnowledgeSearch(previewQuery.value, ["platform", "dataset", "personal"])).hits; if (!previewHits.value.length) message.info("没有召回相关资料"); } catch (error) { message.error((error as Error).message); } finally { previewing.value = false; } }

onMounted(async () => { await Promise.all([datasets.loadAll(), loadDocuments()]); });
onBeforeUnmount(() => window.clearTimeout(refreshTimer));
</script>

<style scoped>
.knowledge-note { margin-bottom: 16px; }
.knowledge-grid { display: grid; grid-template-columns: 330px minmax(0, 1fr); gap: 18px; align-items: start; }
.upload-card, .library-card { padding: 18px; }
.upload-card { position: sticky; top: 82px; }
.selected-file { color: #64748b; margin-top: 8px; }
.library-head { display: flex; justify-content: space-between; gap: 12px; align-items: center; margin-bottom: 12px; }
.document-icon { font-size: 24px; color: #1677ff; }
.document-meta { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; color: #64748b; margin: 6px 0; }
.danger-link { color: #ff4d4f; }
.preview-list { margin-top: 10px; max-height: 300px; overflow-y: auto; }
@media (max-width: 900px) { .knowledge-grid { grid-template-columns: 1fr; } .upload-card { position: static; } }
</style>
