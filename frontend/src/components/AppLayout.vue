<template>
  <a-layout class="research-shell">
    <a-layout-sider class="research-sider" width="264">
      <div class="brand">
        <div class="brand-mark">SC</div>
        <div>
          <div class="brand-title">ANN Research</div>
          <div class="brand-subtitle">Single-cell retrieval platform</div>
        </div>
      </div>
      <a-menu class="research-menu" mode="inline" :selected-keys="[activeKey]" @click="onMenuClick">
        <a-menu-item key="/overview"><DashboardOutlined />Overview</a-menu-item>
        <a-menu-item key="/datasets"><DatabaseOutlined />Datasets</a-menu-item>
        <a-menu-item key="/index-lab"><ExperimentOutlined />Index Lab</a-menu-item>
        <a-menu-item key="/query-lab"><SearchOutlined />Query Lab</a-menu-item>
        <a-menu-item key="/evaluation"><BarChartOutlined />Evaluation</a-menu-item>
        <a-menu-item key="/access"><SafetyCertificateOutlined />Access</a-menu-item>
        <a-menu-item key="/ai-analysis"><RobotOutlined />AI Analysis</a-menu-item>
      </a-menu>
      <div class="sider-capability">
        <div class="capability-title">Capability Map</div>
        <div v-for="capability in capabilities" :key="capability.key" class="capability-row">
          <span>{{ capability.title }}</span>
          <a-tag :color="capability.status === 'ready' ? 'green' : 'default'">{{ capability.status }}</a-tag>
        </div>
      </div>
    </a-layout-sider>
    <a-layout>
      <a-layout-header class="research-header">
        <div class="header-left">
          <a-button class="mobile-nav-trigger" @click="openNav = true">
            <MenuOutlined />
          </a-button>
          <span class="environment-pill">Research Workspace</span>
          <span class="header-note">HNSW baseline · dataset-scoped access · extensible ANN modules</span>
        </div>
        <div class="header-actions">
          <a-badge :count="taskStore.active.length" size="small">
            <a-button @click="openTasks = true"><ClockCircleOutlined />Tasks</a-button>
          </a-badge>
          <a-dropdown>
            <a-button>{{ auth.user?.username }} <DownOutlined /></a-button>
            <template #overlay>
              <a-menu>
                <a-menu-item key="role">Role: {{ auth.user?.role }}</a-menu-item>
                <a-menu-divider />
                <a-menu-item key="logout" @click="logout">Logout</a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </div>
      </a-layout-header>
      <a-layout-content class="research-content">
        <router-view />
      </a-layout-content>
    </a-layout>
    <a-drawer v-model:open="openNav" title="ANN Research" placement="left" width="282">
      <a-menu class="drawer-menu" mode="inline" :selected-keys="[activeKey]" @click="onDrawerMenuClick">
        <a-menu-item key="/overview"><DashboardOutlined />Overview</a-menu-item>
        <a-menu-item key="/datasets"><DatabaseOutlined />Datasets</a-menu-item>
        <a-menu-item key="/index-lab"><ExperimentOutlined />Index Lab</a-menu-item>
        <a-menu-item key="/query-lab"><SearchOutlined />Query Lab</a-menu-item>
        <a-menu-item key="/evaluation"><BarChartOutlined />Evaluation</a-menu-item>
        <a-menu-item key="/access"><SafetyCertificateOutlined />Access</a-menu-item>
        <a-menu-item key="/ai-analysis"><RobotOutlined />AI Analysis</a-menu-item>
      </a-menu>
    </a-drawer>
    <a-drawer v-model:open="openTasks" title="Task Center" width="420">
      <a-list :data-source="taskStore.recent" :loading="taskLoading">
        <template #renderItem="{ item }">
          <a-list-item>
            <a-list-item-meta :title="taskTitle(item)" :description="item.message || item.dataset_name || '-'">
              <template #avatar><a-tag :color="statusColor(item.status)">{{ statusText(item.status) }}</a-tag></template>
            </a-list-item-meta>
            <a-progress v-if="['pending', 'running'].includes(item.status)" type="circle" :percent="item.progress || 0" :size="34" />
          </a-list-item>
        </template>
      </a-list>
    </a-drawer>
  </a-layout>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  BarChartOutlined,
  ClockCircleOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  DownOutlined,
  ExperimentOutlined,
  MenuOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
} from "@ant-design/icons-vue";
import { message } from "ant-design-vue";
import { capabilities } from "@/services/capabilities";
import { useAuthStore } from "@/stores/auth";
import { useTaskStore } from "@/stores/tasks";
import { statusColor, statusText } from "@/utils/format";
import type { TaskRecord } from "@/types";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const taskStore = useTaskStore();
const openNav = ref(false);
const openTasks = ref(false);
const taskLoading = ref(false);

const activeKey = computed(() => {
  if (route.path.startsWith("/datasets")) return "/datasets";
  return route.path;
});

function onMenuClick(event: { key: string }) {
  router.push(event.key);
}

function onDrawerMenuClick(event: { key: string }) {
  openNav.value = false;
  router.push(event.key);
}

function taskTitle(task: TaskRecord) {
  const typeMap: Record<string, string> = { process: "Process dataset", build_index: "Build index" };
  return `${typeMap[task.type] || task.type}${task.dataset_name ? ` · ${task.dataset_name}` : ""}`;
}

async function logout() {
  await auth.logout();
  message.success("已退出登录");
  router.push("/login");
}

watch(openTasks, async (value) => {
  if (!value) return;
  taskLoading.value = true;
  try {
    await taskStore.refreshRecent();
  } finally {
    taskLoading.value = false;
  }
});

onMounted(() => {
  taskStore.startActivePolling();
  taskStore.refreshRecent();
});
</script>
