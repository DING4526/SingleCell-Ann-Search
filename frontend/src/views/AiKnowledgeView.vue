<template>
  <PageHeader title="AI 知识库" description="维护平台、数据集和个人资料；所有内容均按当前账号的访问范围参与召回。">
    <template #actions>
      <a-space>
        <a-button v-if="auth.isAdmin" @click="syncBuiltin">同步内置资料</a-button>
        <a-button :loading="loading" @click="loadDocuments">刷新状态</a-button>
      </a-space>
    </template>
  </PageHeader>

  <a-alert
    class="knowledge-note"
    type="info"
    show-icon
    message="资料只在当前权限范围内召回"
    description="平台资料由管理员维护；数据集资料沿用数据集权限；个人资料仅自己可见。知识内容本身不会获得工具调用权限。"
  />

  <div class="knowledge-grid">
    <section class="surface upload-card">
      <div class="section-title">
        <strong>上传资料</strong>
        <span>支持 PDF、Markdown 和纯文本</span>
      </div>
      <a-form layout="vertical">
        <a-form-item label="知识空间">
          <a-select v-model:value="form.scope" :options="scopeOptions" />
        </a-form-item>
        <a-form-item v-if="form.scope === 'dataset'" label="关联数据集" required>
          <a-select v-model:value="form.dataset_id" :options="editableDatasetOptions" placeholder="选择有编辑权限的数据集" />
        </a-form-item>
        <a-form-item label="标题" extra="留空时使用文件名"><a-input v-model:value="form.title" placeholder="资料标题" /></a-form-item>
        <a-form-item label="说明"><a-textarea v-model:value="form.description" :rows="2" placeholder="资料用途或内容范围" /></a-form-item>
        <a-form-item label="资料文件" required>
          <a-upload-dragger
            accept=".pdf,.md,.markdown,.txt"
            :max-count="1"
            :file-list="uploadFileList"
            :before-upload="beforeUpload"
            @remove="removeUploadFile"
          >
            <p class="upload-title">拖入资料，或点击选择</p>
            <p class="upload-hint">单个 PDF、Markdown 或 TXT 文件</p>
          </a-upload-dragger>
        </a-form-item>
        <a-button type="primary" block :loading="uploading" :disabled="!selectedFile || (form.scope === 'dataset' && !form.dataset_id)" @click="upload">
          上传并建立索引
        </a-button>
      </a-form>

      <a-divider />
      <div class="section-title">
        <strong>检索预览</strong>
        <span>验证当前账号可召回的资料</span>
      </div>
      <a-input-search v-model:value="previewQuery" :loading="previewing" placeholder="输入关键词或研究问题" @search="preview" />
      <a-list v-if="previewHits.length" size="small" :data-source="previewHits" class="preview-list">
        <template #renderItem="{ item }">
          <a-list-item>
            <a-list-item-meta :title="`${item.title}${item.page_number ? ` · 第 ${item.page_number} 页` : ''}`" :description="item.excerpt" />
          </a-list-item>
        </template>
      </a-list>
      <a-empty v-else-if="previewQuery && !previewing" :image="simpleImage" description="暂无匹配资料" />
    </section>

    <section class="surface library-card">
      <div class="library-head">
        <div class="section-title">
          <strong>可访问资料</strong>
          <span>{{ filteredDocuments.length }} 项资料</span>
        </div>
        <a-segmented v-model:value="scopeFilter" :options="filterOptions" />
      </div>

      <a-empty v-if="!loading && !filteredDocuments.length" description="当前空间暂无资料" />
      <a-list v-else class="document-list" :loading="loading" :data-source="filteredDocuments" :locale="{ emptyText: '当前空间暂无资料' }">
        <template #renderItem="{ item }">
          <a-list-item class="document-row">
            <div class="document-summary">
              <div class="document-icon"><FileTextOutlined /></div>
              <div class="document-copy">
                <div class="document-title-row">
                  <strong :title="item.title">{{ item.title }}</strong>
                  <a-tag v-if="isBuiltin(item)" color="blue">内置 · 只读</a-tag>
                </div>
                <p>{{ item.description || item.original_filename || '平台内置研究资料' }}</p>
                <div class="document-meta">
                  <a-tag :color="scopeColor(item.scope)">{{ scopeLabel(item.scope) }}</a-tag>
                  <span v-if="item.dataset_name">{{ item.dataset_name }}</span>
                  <StatusTag :status="item.status" />
                  <a-tag :color="item.semantic_status === 'ready' ? 'purple' : item.semantic_status === 'pending' ? 'processing' : 'default'">
                    {{ semanticStatusText(item.semantic_status) }}
                  </a-tag>
                  <span>{{ item.chunk_count }} 个片段</span>
                  <span v-if="item.page_count">{{ item.page_count }} 页</span>
                  <span>{{ formatBytes(item.size_bytes) }}</span>
                  <span>更新于 {{ formatDate(item.updated_at) }}</span>
                </div>
                <a-alert v-if="item.error_message" class="document-error" type="warning" :message="item.error_message" show-icon />
              </div>
            </div>

            <a-dropdown placement="bottomRight">
              <a-button size="small">操作</a-button>
              <template #overlay>
                <a-menu>
                  <a-menu-item><a :href="`/api/ai/knowledge/documents/${item.id}/file`">查看原文</a></a-menu-item>
                  <a-menu-item v-if="!isBuiltin(item) && item.can_manage" @click="reindex(item.id)">重建索引</a-menu-item>
                  <a-menu-divider v-if="!isBuiltin(item) && item.can_manage" />
                  <a-menu-item
                    v-if="!isBuiltin(item) && item.can_manage"
                    danger
                    :disabled="!item.can_delete"
                    :title="deleteBlockerText(item)"
                    @click="confirmRemove(item)"
                  >永久删除</a-menu-item>
                </a-menu>
              </template>
            </a-dropdown>
          </a-list-item>
        </template>
      </a-list>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { FileTextOutlined } from "@ant-design/icons-vue";
import { Empty, Modal, message } from "ant-design-vue";
import PageHeader from "@/components/PageHeader.vue";
import StatusTag from "@/components/StatusTag.vue";
import { api } from "@/services/api";
import { useAuthStore } from "@/stores/auth";
import { useDatasetStore } from "@/stores/datasets";
import { formatDate } from "@/utils/format";
import type { KnowledgeDocument, KnowledgeHit } from "@/types";

type DeleteBlockerInfo = string | { label?: string; count?: number; type?: string };
type ManagedKnowledgeDocument = KnowledgeDocument & {
  can_manage?: boolean;
  is_builtin?: boolean;
};

const auth = useAuthStore();
const datasets = useDatasetStore();
const simpleImage = Empty.PRESENTED_IMAGE_SIMPLE;
const documents = ref<ManagedKnowledgeDocument[]>([]);
const loading = ref(false);
const uploading = ref(false);
const selectedFile = ref<File>();
const scopeFilter = ref("all");
const previewQuery = ref("");
const previewing = ref(false);
const previewHits = ref<KnowledgeHit[]>([]);
const form = reactive<{ scope: "personal" | "dataset" | "platform"; dataset_id?: number; title: string; description: string }>({ scope: "personal", title: "", description: "" });
let refreshTimer: number | undefined;

const uploadFileList = computed(() => selectedFile.value ? [{ uid: "knowledge-file", name: selectedFile.value.name, status: "done" }] : []);
const scopeOptions = computed(() => [
  { value: "personal", label: "个人知识（仅自己）" },
  { value: "dataset", label: "数据集知识（沿用数据权限）" },
  ...(auth.isAdmin ? [{ value: "platform", label: "平台知识（全部 AI 用户）" }] : []),
]);
const editableDatasetOptions = computed(() => datasets.datasets.filter((item) => item.can_edit).map((item) => ({ value: item.id, label: item.name })));
const filterOptions = [
  { value: "all", label: "全部" }, { value: "platform", label: "平台" },
  { value: "dataset", label: "数据集" }, { value: "personal", label: "个人" },
];
const filteredDocuments = computed(() => documents.value.filter((item) => scopeFilter.value === "all" || item.scope === scopeFilter.value));

function beforeUpload(file: File) {
  selectedFile.value = file;
  return false;
}
function removeUploadFile() {
  selectedFile.value = undefined;
  return true;
}
function formatBytes(value: number) {
  if (!value) return "0 B";
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}
function scopeLabel(scope: string) { return ({ platform: "平台", dataset: "数据集", personal: "个人" } as Record<string, string>)[scope] || "其他"; }
function scopeColor(scope: string) { return ({ platform: "blue", dataset: "cyan", personal: "green" } as Record<string, string>)[scope] || "default"; }
function semanticStatusText(status: string) {
  return ({
    ready: "语义索引可用",
    pending: "语义索引等待中",
    error: "关键词索引可用",
    not_configured: "关键词索引可用",
  } as Record<string, string>)[status] || "索引状态未知";
}
function isBuiltin(item: ManagedKnowledgeDocument) { return item.is_builtin === true || item.source_type === "builtin"; }
function deleteBlockerText(item: ManagedKnowledgeDocument) {
  if (item.can_delete) return "";
  const blockers = (item.delete_blockers || []) as unknown as DeleteBlockerInfo[];
  return blockers.map((blocker) => {
    if (typeof blocker === "string") return blocker;
    return `${blocker.label || "存在依赖"}${blocker.count ? `（${blocker.count}）` : ""}`;
  }).join("；") || "资料正在处理，暂时不能删除";
}

async function loadDocuments() {
  loading.value = true;
  window.clearTimeout(refreshTimer);
  try {
    documents.value = (await api.knowledgeDocuments()).documents as ManagedKnowledgeDocument[];
    if (documents.value.some((item) => ["pending", "extracting", "indexing"].includes(item.status))) {
      refreshTimer = window.setTimeout(loadDocuments, 2200);
    }
  } catch (error) {
    message.error((error as Error).message);
  } finally {
    loading.value = false;
  }
}

async function upload() {
  if (!selectedFile.value) return;
  uploading.value = true;
  try {
    await api.uploadKnowledgeDocument({ file: selectedFile.value, ...form });
    message.success("资料已上传，正在建立索引");
    selectedFile.value = undefined;
    form.title = "";
    form.description = "";
    await loadDocuments();
  } catch (error) {
    message.error((error as Error).message);
  } finally {
    uploading.value = false;
  }
}

async function reindex(id: number) {
  try {
    await api.reindexKnowledgeDocument(id);
    message.success("已提交索引重建");
    await loadDocuments();
  } catch (error) { message.error((error as Error).message); }
}

function confirmRemove(item: ManagedKnowledgeDocument) {
  if (!item.can_delete) return;
  Modal.confirm({
    title: `永久删除“${item.title}”？`,
    content: "资料文件、文本片段和语义索引将被移除，此后 AI 不再召回该资料。此操作不可撤销。",
    okText: "永久删除",
    okType: "danger",
    cancelText: "取消",
    async onOk() {
      try {
        await api.deleteKnowledgeDocument(item.id);
        await loadDocuments();
        message.success("资料已删除");
      } catch (error) {
        message.error((error as Error).message);
        throw error;
      }
    },
  });
}

async function syncBuiltin() {
  try {
    await api.syncBuiltinKnowledge();
    message.success("内置资料已同步");
    await loadDocuments();
  } catch (error) { message.error((error as Error).message); }
}

async function preview() {
  if (!previewQuery.value.trim()) return;
  previewing.value = true;
  try {
    previewHits.value = (await api.previewKnowledgeSearch(previewQuery.value.trim(), ["platform", "dataset", "personal"])).hits;
  } catch (error) {
    message.error((error as Error).message);
  } finally {
    previewing.value = false;
  }
}

onMounted(async () => { await Promise.all([datasets.loadAll(), loadDocuments()]); });
onBeforeUnmount(() => window.clearTimeout(refreshTimer));
</script>

<style scoped>
.knowledge-note { margin-bottom: 16px; }
.knowledge-grid { display: grid; grid-template-columns: 340px minmax(0, 1fr); gap: 18px; align-items: start; }
.upload-card, .library-card { padding: 18px; }
.upload-card { position: sticky; top: 82px; }
.section-title { display: grid; gap: 2px; margin-bottom: 14px; }
.section-title strong { color: #2e3c51; font-size: 15px; }
.section-title span { color: #8491a3; font-size: 11px; }
.library-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 42px; margin-bottom: 6px; }
.library-head .section-title { margin-bottom: 0; }
.document-list :deep(.ant-list-item) { align-items: flex-start; gap: 14px; padding: 15px 0; }
.document-summary { display: grid; grid-template-columns: 38px minmax(0, 1fr); gap: 12px; min-width: 0; flex: 1; }
.document-icon { display: grid; width: 38px; height: 38px; place-items: center; border-radius: 9px; background: #edf4fb; color: #27669f; font-size: 18px; }
.document-copy { min-width: 0; }
.document-title-row { display: flex; align-items: center; gap: 8px; min-width: 0; }
.document-title-row strong { min-width: 0; overflow: hidden; color: #2e3c51; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.document-title-row :deep(.ant-tag) { flex: 0 0 auto; margin-inline-end: 0; }
.document-copy > p { display: -webkit-box; margin: 4px 0 7px; overflow: hidden; color: #6f7d91; font-size: 12px; line-height: 1.5; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.document-meta { display: flex; align-items: center; gap: 6px; min-width: 0; flex-wrap: wrap; color: #8290a3; font-size: 11px; }
.document-meta :deep(.ant-tag) { margin-inline-end: 0; }
.document-error { margin-top: 9px; }
.preview-list { max-height: 300px; margin-top: 10px; overflow-y: auto; }
.preview-list :deep(.ant-list-item-meta-title) { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.preview-list :deep(.ant-list-item-meta-description) { display: -webkit-box; overflow: hidden; -webkit-box-orient: vertical; -webkit-line-clamp: 3; }
</style>
