<template>
  <a-layout class="research-shell">
    <a-layout-sider class="research-sider" width="264">
      <div class="brand">
        <div class="brand-mark">SC</div>
        <div>
          <div class="brand-title">ANN 研究平台</div>
          <div class="brand-subtitle">单细胞检索研究平台</div>
        </div>
      </div>
      <a-menu class="research-menu" mode="inline" :selected-keys="[activeKey]" @click="onMenuClick">
        <a-menu-item key="/overview"><DashboardOutlined />概览</a-menu-item>
        <a-menu-item key="/datasets"><DatabaseOutlined />数据资源</a-menu-item>
        <a-menu-item key="/index-lab"><ExperimentOutlined />索引实验室</a-menu-item>
        <a-menu-item key="/joint-indexes"><DeploymentUnitOutlined />联合索引</a-menu-item>
        <a-menu-item key="/query-lab"><SearchOutlined />检索实验室</a-menu-item>
        <a-menu-item key="/access"><SafetyCertificateOutlined />权限管理</a-menu-item>
        <a-menu-item key="/ai-analysis"><RobotOutlined />AI 分析</a-menu-item>
      </a-menu>
      <div class="sider-capability">
        <div class="capability-title">能力地图</div>
        <div v-for="capability in capabilities" :key="capability.key" class="capability-row">
          <span>{{ capability.title }}</span>
          <a-tag :color="capability.status === 'ready' ? 'green' : 'default'">{{ statusText(capability.status) }}</a-tag>
        </div>
      </div>
    </a-layout-sider>
    <a-layout>
      <a-layout-header class="research-header">
        <div class="header-left">
          <a-button class="mobile-nav-trigger" @click="openNav = true">
            <MenuOutlined />
          </a-button>
          <span class="environment-pill">研究工作台</span>
          <span class="header-note">HNSW 基线 · 数据集级访问 · 可扩展 ANN 模块</span>
        </div>
        <div class="header-actions">
          <a-badge :count="taskStore.active.length" size="small">
            <a-button @click="openTasks = true"><ClockCircleOutlined />任务</a-button>
          </a-badge>
          <a-dropdown>
            <a-button>{{ auth.user?.username }} <DownOutlined /></a-button>
            <template #overlay>
              <a-menu>
                <a-menu-item key="role">角色：{{ roleText(auth.user?.role) }}</a-menu-item>
                <a-menu-item key="change-password" @click="passwordOpen = true">修改密码</a-menu-item>
                <a-menu-divider />
                <a-menu-item key="logout" @click="logout">退出登录</a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </div>
      </a-layout-header>
      <a-layout-content class="research-content">
        <router-view />
      </a-layout-content>
    </a-layout>
    <a-drawer v-model:open="openNav" title="ANN 研究平台" placement="left" width="282">
      <a-menu class="drawer-menu" mode="inline" :selected-keys="[activeKey]" @click="onDrawerMenuClick">
        <a-menu-item key="/overview"><DashboardOutlined />概览</a-menu-item>
        <a-menu-item key="/datasets"><DatabaseOutlined />数据资源</a-menu-item>
        <a-menu-item key="/index-lab"><ExperimentOutlined />索引实验室</a-menu-item>
        <a-menu-item key="/joint-indexes"><DeploymentUnitOutlined />联合索引</a-menu-item>
        <a-menu-item key="/query-lab"><SearchOutlined />检索实验室</a-menu-item>
        <a-menu-item key="/access"><SafetyCertificateOutlined />权限管理</a-menu-item>
        <a-menu-item key="/ai-analysis"><RobotOutlined />AI 分析</a-menu-item>
      </a-menu>
    </a-drawer>
    <a-drawer v-model:open="openTasks" title="任务中心" width="420">
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
    <a-modal v-model:open="passwordOpen" title="修改密码" ok-text="确认修改" :confirm-loading="passwordLoading" @ok="changePassword">
      <a-form layout="vertical">
        <a-form-item label="当前密码"><a-input-password v-model:value="passwordForm.oldPassword" autocomplete="current-password" /></a-form-item>
        <a-form-item label="新密码"><a-input-password v-model:value="passwordForm.newPassword" autocomplete="new-password" /></a-form-item>
        <a-form-item label="确认新密码"><a-input-password v-model:value="passwordForm.confirm" autocomplete="new-password" /></a-form-item>
      </a-form>
    </a-modal>
  </a-layout>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  ClockCircleOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  DeploymentUnitOutlined,
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
import { roleText, statusColor, statusText, taskTypeText } from "@/utils/format";
import type { TaskRecord } from "@/types";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const taskStore = useTaskStore();
const openNav = ref(false);
const openTasks = ref(false);
const taskLoading = ref(false);
const passwordOpen = ref(false);
const passwordLoading = ref(false);
const passwordForm = reactive({ oldPassword: "", newPassword: "", confirm: "" });

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
  return `${taskTypeText(task.type)}${task.dataset_name ? ` · ${task.dataset_name}` : ""}`;
}

async function logout() {
  await auth.logout();
  message.success("已退出登录");
  router.push("/login");
}

async function changePassword() {
  if (passwordForm.newPassword.length < 4) return message.warning("新密码至少 4 位");
  if (passwordForm.newPassword !== passwordForm.confirm) return message.warning("两次输入的新密码不一致");
  passwordLoading.value = true;
  try {
    await auth.changePassword(passwordForm.oldPassword, passwordForm.newPassword, passwordForm.confirm);
    message.success("密码已更新");
    passwordOpen.value = false;
    Object.assign(passwordForm, { oldPassword: "", newPassword: "", confirm: "" });
  } catch (error) {
    message.error((error as Error).message);
  } finally {
    passwordLoading.value = false;
  }
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
