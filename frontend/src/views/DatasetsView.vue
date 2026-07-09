<template>
  <PageHeader title="Datasets" description="管理单细胞数据资源，追踪处理状态、向量维度、索引数量和访问属性。">
    <template #actions>
      <a-space>
        <a-input-search v-model:value="keyword" placeholder="搜索数据集" style="width: 240px" />
        <a-button type="primary" @click="uploadOpen = true">上传数据集</a-button>
      </a-space>
    </template>
  </PageHeader>

  <div class="surface">
    <div class="toolbar">
      <span class="toolbar-title">Dataset Resources</span>
      <a-segmented v-model:value="statusFilter" :options="statusOptions" />
    </div>
    <a-table :loading="store.loading" :data-source="filteredDatasets" :columns="columns" row-key="id" size="middle" :scroll="{ x: 980 }">
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'name'">
          <a-space direction="vertical" size="small">
            <a @click="$router.push(`/datasets/${record.id}`)">{{ record.name }}</a>
            <span class="muted">{{ record.description || "No description" }}</span>
          </a-space>
        </template>
        <template v-else-if="column.key === 'status'"><StatusTag :status="record.status" /></template>
        <template v-else-if="column.key === 'access'">
          <a-tag>{{ record.owner_id ? record.visibility : "legacy" }}</a-tag>
        </template>
        <template v-else-if="column.key === 'actions'">
          <a-space>
            <a-button size="small" @click="$router.push(`/datasets/${record.id}`)">Open</a-button>
            <a-popconfirm title="删除该数据集及关联索引文件？" ok-text="删除" cancel-text="取消" @confirm="remove(record.id)">
              <a-button size="small" danger :disabled="!record.can_manage">Delete</a-button>
            </a-popconfirm>
          </a-space>
        </template>
      </template>
    </a-table>
  </div>

  <a-drawer v-model:open="uploadOpen" title="Upload AnnData Dataset" width="520">
    <a-form layout="vertical" @finish="submitUpload">
      <a-form-item label="数据集名称">
        <a-input v-model:value="uploadForm.name" placeholder="例如 demo_liver" />
      </a-form-item>
      <a-form-item label="描述">
        <a-input v-model:value="uploadForm.description" placeholder="研究队列、组织来源或实验说明" />
      </a-form-item>
      <a-form-item label=".h5ad 文件" required>
        <input type="file" accept=".h5ad" @change="onFileChange" />
      </a-form-item>
      <a-alert message="建议上传前确认 AnnData 包含 X_pca；X_umap 可用于更好的可视化。" type="info" show-icon />
      <div style="margin-top: 18px">
        <a-button type="primary" html-type="submit" :loading="uploading" block>上传并注册</a-button>
      </div>
    </a-form>
  </a-drawer>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { message } from "ant-design-vue";
import PageHeader from "@/components/PageHeader.vue";
import StatusTag from "@/components/StatusTag.vue";
import { useDatasetStore } from "@/stores/datasets";
import { formatDate, numberOrDash } from "@/utils/format";
import type { Dataset } from "@/types";

const store = useDatasetStore();
const uploadOpen = ref(false);
const uploading = ref(false);
const keyword = ref("");
const statusFilter = ref("all");
const uploadFile = ref<File | null>(null);
const uploadForm = reactive({ name: "", description: "" });
const statusOptions = [
  { label: "All", value: "all" },
  { label: "Uploaded", value: "uploaded" },
  { label: "Processed", value: "processed" },
  { label: "Indexed", value: "indexed" },
  { label: "Error", value: "error" },
];

const columns = [
  { title: "Dataset", key: "name", width: 280 },
  { title: "Cells", dataIndex: "n_cells", customRender: ({ text }: { text: number | null }) => numberOrDash(text), width: 110 },
  { title: "Genes", dataIndex: "n_genes", customRender: ({ text }: { text: number | null }) => numberOrDash(text), width: 110 },
  { title: "PCA Dim", dataIndex: "vector_dim", customRender: ({ text }: { text: number | null }) => numberOrDash(text), width: 110 },
  { title: "Indexes", dataIndex: "ready_index_count", width: 100 },
  { title: "Access", key: "access", width: 110 },
  { title: "Status", key: "status", width: 120 },
  { title: "Created", dataIndex: "created_at", customRender: ({ text }: { text: string | null }) => formatDate(text), width: 140 },
  { title: "Actions", key: "actions", fixed: "right", width: 150 },
];

const filteredDatasets = computed(() => {
  const term = keyword.value.trim().toLowerCase();
  return store.datasets.filter((dataset) => {
    const matchStatus = statusFilter.value === "all" || dataset.status === statusFilter.value;
    const matchTerm = !term || dataset.name.toLowerCase().includes(term) || dataset.description.toLowerCase().includes(term);
    return matchStatus && matchTerm;
  });
});

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  uploadFile.value = input.files?.[0] || null;
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
    window.location.href = `/datasets/${id}`;
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

onMounted(store.loadAll);
</script>
