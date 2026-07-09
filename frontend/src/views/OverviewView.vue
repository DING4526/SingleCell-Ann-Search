<template>
  <PageHeader title="Overview" description="研究工作台汇总数据资源、索引状态、任务和可扩展能力模块。">
    <template #actions>
      <a-space>
        <a-button @click="reload">刷新</a-button>
        <a-button type="primary" @click="$router.push('/datasets')">管理数据资源</a-button>
      </a-space>
    </template>
  </PageHeader>

  <div class="metric-grid">
    <div class="metric-tile"><div class="metric-label">Datasets</div><div class="metric-value">{{ summary.datasets_total || 0 }}</div></div>
    <div class="metric-tile"><div class="metric-label">Processed</div><div class="metric-value">{{ processedTotal }}</div></div>
    <div class="metric-tile"><div class="metric-label">Ready Indexes</div><div class="metric-value">{{ summary.indexes_total || 0 }}</div></div>
    <div class="metric-tile"><div class="metric-label">Queries</div><div class="metric-value">{{ summary.recent_queries || 0 }}</div></div>
  </div>

  <div class="two-column">
    <div class="surface">
      <div class="toolbar"><span class="toolbar-title">Recent Datasets</span><a-button size="small" @click="$router.push('/datasets')">Open</a-button></div>
      <a-table size="small" :pagination="false" :data-source="recentDatasets" :columns="datasetColumns" row-key="id">
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'name'">
            <a @click="$router.push(`/datasets/${record.id}`)">{{ record.name }}</a>
          </template>
          <template v-if="column.key === 'status'"><StatusTag :status="record.status" /></template>
        </template>
      </a-table>
    </div>
    <div class="surface">
      <div class="toolbar"><span class="toolbar-title">Capability Roadmap</span></div>
      <div class="surface-pad capability-list">
        <div v-for="capability in capabilities" :key="capability.key" class="capability-card">
          <a-tag :color="capability.status === 'ready' ? 'green' : 'default'">{{ capability.status }}</a-tag>
          <h3>{{ capability.title }}</h3>
          <p class="muted">{{ capability.description }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { api } from "@/services/api";
import { capabilities } from "@/services/capabilities";
import PageHeader from "@/components/PageHeader.vue";
import StatusTag from "@/components/StatusTag.vue";

const summary = ref<Record<string, any>>({});
const recentDatasets = computed(() => summary.value.recent_datasets || []);
const processedTotal = computed(() => (summary.value.datasets_processed || 0) + (summary.value.datasets_indexed || 0));
const datasetColumns = [
  { title: "Name", dataIndex: "name", key: "name" },
  { title: "Status", dataIndex: "status", key: "status", width: 120 },
  { title: "Cells", dataIndex: "n_cells", key: "n_cells", width: 100 },
];

async function reload() {
  const data = await api.dashboardSummary();
  summary.value = data;
}

onMounted(reload);
</script>
