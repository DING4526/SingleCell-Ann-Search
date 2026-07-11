<template>
  <PageHeader title="数据资源" description="管理单细胞数据资源，追踪处理状态、向量维度、索引数量和访问属性。">
    <template #actions>
      <a-space>
        <a-input-search v-model:value="keyword" placeholder="搜索数据集" style="width: 240px" />
        <a-button type="primary" @click="uploadOpen = true">上传数据集</a-button>
      </a-space>
    </template>
  </PageHeader>

  <div class="surface">
    <div class="toolbar">
      <span class="toolbar-title">数据资源清单</span>
      <a-segmented v-model:value="statusFilter" :options="statusOptions" />
    </div>
    <a-alert v-if="pageError" class="list-error" type="error" show-icon :message="pageError">
      <template #action><a-button size="small" @click="loadDatasets">重试</a-button></template>
    </a-alert>
    <div class="table-shell">
      <a-table class="compact-table dataset-table" :loading="store.loading" :data-source="filteredDatasets" :columns="columns" row-key="id" size="small" :locale="{ emptyText: '暂无符合条件的数据集' }">
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'name'">
          <router-link class="dataset-name" :to="`/datasets/${record.id}`">{{ record.name }}</router-link>
          <div v-if="record.description" class="dataset-description">{{ record.description }}</div>
        </template>
        <template v-else-if="column.key === 'status'"><StatusTag :status="record.status" /></template>
        <template v-else-if="column.key === 'access'">
          <a-tag :color="record.effective_role === 'owner' ? 'purple' : record.effective_role === 'editor' ? 'green' : record.effective_role === 'admin' ? 'red' : 'blue'">{{ accessText(record.effective_role) }}</a-tag>
        </template>
        <template v-else-if="column.key === 'actions'">
          <a-dropdown trigger="click">
            <a-button size="small">操作</a-button>
            <template #overlay>
              <a-menu>
                <a-menu-item @click="$router.push(`/datasets/${record.id}`)">查看详情</a-menu-item>
                <a-menu-divider />
                <a-menu-item danger :disabled="!canDeleteResource(record, record.can_manage)" @click="confirmRemove(record)">永久删除</a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </template>
      </template>
      </a-table>
    </div>
  </div>

  <a-drawer v-model:open="uploadOpen" title="上传 AnnData 数据集" width="min(540px, 96vw)">
    <a-form layout="vertical">
      <a-form-item label="数据集名称">
        <a-input v-model:value="uploadForm.name" placeholder="例如 demo_liver" />
      </a-form-item>
      <a-form-item label="描述">
        <a-input v-model:value="uploadForm.description" placeholder="研究队列、组织来源或实验说明" />
      </a-form-item>
      <a-form-item label="AnnData 文件" required>
        <a-upload-dragger
          accept=".h5ad"
          :max-count="1"
          :file-list="uploadFileList"
          :before-upload="beforeUpload"
          @remove="removeUploadFile"
        >
          <p class="upload-title">拖入 .h5ad 文件，或点击选择</p>
          <p class="upload-hint">文件仅用于当前平台的数据处理与索引构建</p>
        </a-upload-dragger>
      </a-form-item>
      <a-alert message="建议上传前确认 AnnData 包含 X_pca；X_umap 可用于更好的可视化。" type="info" show-icon />
      <div style="margin-top: 18px">
        <a-button type="primary" :loading="uploading" block @click="submitUpload">上传并注册</a-button>
      </div>
    </a-form>
  </a-drawer>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { message, Modal } from "ant-design-vue";
import PageHeader from "@/components/PageHeader.vue";
import StatusTag from "@/components/StatusTag.vue";
import { useDatasetStore } from "@/stores/datasets";
import { formatDate, numberOrDash } from "@/utils/format";
import { canDeleteResource, deletionConfirmationDescription } from "@/utils/resource-actions";
import type { Dataset } from "@/types";

const store = useDatasetStore();
const router = useRouter();
const uploadOpen = ref(false);
const uploading = ref(false);
const pageError = ref("");
const keyword = ref("");
const statusFilter = ref("all");
const uploadFile = ref<File | null>(null);
const uploadFileList = computed(() => uploadFile.value ? [{ uid: "selected", name: uploadFile.value.name, status: "done" }] : []);
const uploadForm = reactive({ name: "", description: "" });
const statusOptions = [
  { label: "全部", value: "all" },
  { label: "已上传", value: "uploaded" },
  { label: "已处理", value: "processed" },
  { label: "已建索引", value: "indexed" },
  { label: "错误", value: "error" },
];

const columns = [
  { title: "数据集", key: "name" },
  { title: "细胞数", dataIndex: "n_cells", customRender: ({ text }: { text: number | null }) => numberOrDash(text), width: 96, align: "right" },
  { title: "基因数", dataIndex: "n_genes", customRender: ({ text }: { text: number | null }) => numberOrDash(text), width: 96, align: "right" },
  { title: "PCA", dataIndex: "vector_dim", customRender: ({ text }: { text: number | null }) => numberOrDash(text), width: 72, align: "right" },
  { title: "索引", dataIndex: "ready_index_count", width: 72, align: "right" },
  { title: "访问", key: "access", width: 84 },
  { title: "状态", key: "status", width: 92 },
  { title: "创建", dataIndex: "created_at", customRender: ({ text }: { text: string | null }) => formatDate(text), width: 104 },
  { title: "操作", key: "actions", width: 76, align: "center" },
];

const filteredDatasets = computed(() => {
  const term = keyword.value.trim().toLowerCase();
  return store.datasets.filter((dataset) => {
    const matchStatus = statusFilter.value === "all" || dataset.status === statusFilter.value;
    const matchTerm = !term || dataset.name.toLowerCase().includes(term) || dataset.description.toLowerCase().includes(term);
    return matchStatus && matchTerm;
  });
});

function accessText(role?: string | null) {
  return ({ admin: "管理员", owner: "所有者", editor: "可编辑", viewer: "只读" } as Record<string, string>)[role || ""] || "-";
}

function beforeUpload(file: File) {
  if (!file.name.toLowerCase().endsWith(".h5ad")) {
    message.error("请选择 .h5ad 文件");
    return false;
  }
  uploadFile.value = file;
  if (!uploadForm.name.trim()) uploadForm.name = file.name.replace(/\.h5ad$/i, "");
  return false;
}

function removeUploadFile() {
  uploadFile.value = null;
  return true;
}

async function submitUpload() {
  if (!uploadFile.value) {
    message.warning("请选择 .h5ad 文件");
    return;
  }
  uploading.value = true;
  try {
    const form = new FormData();
    form.set("file", uploadFile.value);
    form.set("name", uploadForm.name);
    form.set("description", uploadForm.description);
    const id = await store.upload(form);
    message.success("数据集已上传");
    uploadOpen.value = false;
    uploadForm.name = "";
    uploadForm.description = "";
    uploadFile.value = null;
    await router.push(`/datasets/${id}`);
  } catch (error) {
    message.error((error as Error).message);
  } finally {
    uploading.value = false;
  }
}

async function remove(id: number) {
  try {
    await store.remove(id);
    message.success("数据集已删除");
  } catch (error) {
    message.error((error as Error).message);
  }
}

function confirmRemove(record: Dataset) {
  const blockers = record.delete_blockers || [];
  Modal.confirm({
    title: `永久删除「${record.name}」？`,
    content: deletionConfirmationDescription(record, "关联细胞、索引和受管文件也会被删除，且无法恢复。"),
    okText: "永久删除",
    okType: "danger",
    cancelText: "取消",
    okButtonProps: { disabled: blockers.length > 0 },
    onOk: () => remove(record.id),
  });
}

async function loadDatasets() {
  pageError.value = "";
  try {
    await store.loadAll();
  } catch (error) {
    pageError.value = (error as Error).message;
  }
}

onMounted(loadDatasets);
</script>

<style scoped>
.list-error { margin: 12px 14px 0; }
.dataset-name { color: #0f6f78; font-weight: 600; }
.dataset-description { margin-top: 3px; max-width: 300px; overflow: hidden; color: #64748b; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.upload-title { margin: 4px 0; color: #334155; font-weight: 600; }
.upload-hint { margin: 0; color: #94a3b8; font-size: 12px; }
</style>
