<template>
  <PageHeader title="Access" description="查看当前可访问数据资源。完整用户、共享和权限策略管理将在后续模块接入。" />

  <div class="surface">
    <div class="toolbar">
      <span class="toolbar-title">Current Access Scope</span>
      <a-tag>{{ auth.user?.role }}</a-tag>
    </div>
    <a-table :data-source="store.datasets" :columns="columns" row-key="id" size="middle" :loading="store.loading">
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'name'"><a @click="$router.push(`/datasets/${record.id}`)">{{ record.name }}</a></template>
        <template v-if="column.key === 'visibility'"><a-tag>{{ record.owner_name || "legacy" }} / {{ record.visibility }}</a-tag></template>
        <template v-if="column.key === 'manage'"><a-tag :color="record.can_manage ? 'green' : 'default'">{{ record.can_manage ? "manage" : "view" }}</a-tag></template>
      </template>
    </a-table>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from "vue";
import PageHeader from "@/components/PageHeader.vue";
import { useAuthStore } from "@/stores/auth";
import { useDatasetStore } from "@/stores/datasets";

const auth = useAuthStore();
const store = useDatasetStore();
const columns = [
  { title: "Dataset", key: "name" },
  { title: "Access", key: "visibility" },
  { title: "Permission", key: "manage", width: 140 },
  { title: "Status", dataIndex: "status", width: 140 },
];

onMounted(store.loadAll);
</script>
