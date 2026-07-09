<template>
  <PageHeader title="权限管理" description="查看当前可访问数据资源。完整用户、共享和权限策略管理将在后续模块接入。" />

  <div class="surface">
    <div class="toolbar">
      <span class="toolbar-title">当前访问范围</span>
      <a-tag>{{ roleText(auth.user?.role) }}</a-tag>
    </div>
    <a-table :data-source="store.datasets" :columns="columns" row-key="id" size="middle" :loading="store.loading">
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'name'"><a @click="$router.push(`/datasets/${record.id}`)">{{ record.name }}</a></template>
        <template v-if="column.key === 'visibility'"><a-tag>{{ record.owner_name || "旧数据" }} / {{ visibilityText(record.visibility) }}</a-tag></template>
        <template v-if="column.key === 'manage'"><a-tag :color="record.can_manage ? 'green' : 'default'">{{ record.can_manage ? "可管理" : "仅查看" }}</a-tag></template>
        <template v-if="column.key === 'status'"><StatusTag :status="record.status" /></template>
      </template>
    </a-table>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from "vue";
import PageHeader from "@/components/PageHeader.vue";
import StatusTag from "@/components/StatusTag.vue";
import { useAuthStore } from "@/stores/auth";
import { useDatasetStore } from "@/stores/datasets";
import { roleText, visibilityText } from "@/utils/format";

const auth = useAuthStore();
const store = useDatasetStore();
const columns = [
  { title: "数据集", key: "name" },
  { title: "访问范围", key: "visibility" },
  { title: "权限", key: "manage", width: 140 },
  { title: "状态", key: "status", width: 140 },
];

onMounted(store.loadAll);
</script>
