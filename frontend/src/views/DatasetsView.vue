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
    <div class="table-shell">
      <a-table class="compact-table dataset-table" :loading="store.loading" :data-source="filteredDatasets" :columns="columns" row-key="id" size="middle">
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'name'">
          <a-space direction="vertical" size="small">
            <a @click="$router.push(`/datasets/${record.id}`)">{{ record.name }}</a>
            <span class="muted">{{ record.description || "暂无描述" }}</span>
          </a-space>
        </template>
        <template v-else-if="column.key === 'status'"><StatusTag :status="record.status" /></template>
        <template v-else-if="column.key === 'access'">
          <a-tag>{{ record.owner_id ? record.visibility : "旧数据" }}</a-tag>
        </template>
        <template v-else-if="column.key === 'actions'">
          <a-space :size="6" wrap>
            <a-button size="small" @click="$router.push(`/datasets/${record.id}`)">查看</a-button>
            <a-popconfirm title="删除该数据集及关联索引文件？" ok-text="删除" cancel-text="取消" @confirm="remove(record.id)">
              <a-button size="small" danger :disabled="!record.can_manage">删除</a-button>
            </a-popconfirm>
          </a-space>
        </template>
      </template>
      </a-table>
    </div>
  </div>

  <a-drawer v-model:open="uploadOpen" title="上传 AnnData 数据集" width="520">
    <a-form layout="vertical">
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
        <a-button type="primary" :loading="uploading" block @click="submitUpload">上传并注册</a-button>
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
  { label: "全部", value: "all" },
  { label: "已上传", value: "uploaded" },
  { label: "已处理", value: "processed" },
  { label: "已建索引", value: "indexed" },
  { label: "错误", value: "error" },
];

const columns = [
  { title: "数据集", key: "name", width: 220 },
  { title: "细胞数", dataIndex: "n_cells", customRender: ({ text }: { text: number | null }) => numberOrDash(text), width: 88 },
  { title: "基因数", dataIndex: "n_genes", customRender: ({ text }: { text: number | null }) => numberOrDash(text), width: 88 },
  { title: "PCA", dataIndex: "vector_dim", customRender: ({ text }: { text: number | null }) => numberOrDash(text), width: 76 },
  { title: "索引", dataIndex: "ready_index_count", width: 68 },
  { title: "访问", key: "access", width: 84 },
  { title: "状态", key: "status", width: 92 },
  { title: "创建", dataIndex: "created_at", customRender: ({ text }: { text: string | null }) => formatDate(text), width: 104 },
  { title: "操作", key: "actions", width: 118 },
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
