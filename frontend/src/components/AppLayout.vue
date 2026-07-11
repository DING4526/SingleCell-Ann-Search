<template>
  <a-layout class="research-shell">
    <a-layout-sider class="research-sider" width="240" theme="light">
      <div class="brand">
        <div class="brand-mark">SC</div>
        <div class="brand-copy">
          <div class="brand-title">ANN 研究平台</div>
          <div class="brand-subtitle">单细胞检索工作台</div>
        </div>
      </div>

      <nav class="sider-navigation" aria-label="平台主导航">
        <div class="menu-section-label">研究工作台</div>
        <a-menu class="research-menu" mode="inline" :selected-keys="[activeKey]" @click="onMenuClick">
          <a-menu-item key="/overview"><DashboardOutlined />概览</a-menu-item>
          <a-menu-item key="/datasets"><DatabaseOutlined />数据资源</a-menu-item>
          <a-menu-item key="/index-lab"><ExperimentOutlined />索引实验室</a-menu-item>
          <a-menu-item key="/joint-indexes"><DeploymentUnitOutlined />联合索引</a-menu-item>
          <a-menu-item key="/query-lab"><SearchOutlined />检索实验室</a-menu-item>
          <a-menu-item key="/access"><SafetyCertificateOutlined />权限管理</a-menu-item>
          <a-menu-item key="/ai-knowledge"><BookOutlined />AI 知识库</a-menu-item>
          <a-menu-item key="/ai-assistant"><MessageOutlined />AI 助手</a-menu-item>
        </a-menu>
      </nav>

      <div class="sider-footer">
        <span class="sider-footer__dot" />
        <span>科研数据与向量检索</span>
      </div>
    </a-layout-sider>

    <a-layout class="research-main">
      <a-layout-header class="research-header">
        <div class="header-context">
          <span class="environment-pill">研究工作台</span>
          <span class="header-separator">/</span>
          <strong class="header-page-title">{{ currentPageTitle }}</strong>
        </div>
        <div class="header-actions">
          <a-badge :count="taskStore.active.length" :overflow-count="99" size="small">
            <a-button @click="openTasks = true"><ClockCircleOutlined />任务中心</a-button>
          </a-badge>
          <a-dropdown placement="bottomRight">
            <a-button class="account-button">
              <span class="account-avatar">{{ accountInitial }}</span>
              <span>{{ auth.user?.username }}</span>
              <DownOutlined />
            </a-button>
            <template #overlay>
              <a-menu>
                <a-menu-item key="role" disabled>当前角色：{{ roleText(auth.user?.role) }}</a-menu-item>
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

    <a-drawer v-model:open="openTasks" class="task-drawer" title="任务中心" width="460" :body-style="{ padding: 0 }">
      <template #extra>
        <a-popconfirm
          title="从任务历史中移除全部已结束记录？"
          description="正在运行的任务不会受到影响。"
          ok-text="全部移除"
          cancel-text="取消"
          :disabled="!hasTerminalTasks"
          @confirm="clearTerminalTasks"
        >
          <a-button type="link" danger size="small" :disabled="!hasTerminalTasks" :loading="clearingTasks">从历史移除已结束记录</a-button>
        </a-popconfirm>
      </template>

      <div class="task-center-controls">
        <a-segmented v-model:value="taskFilter" :options="taskFilterOptions" />
        <span class="task-count">{{ filteredTasks.length }} 项记录</span>
      </div>

      <a-list
        class="task-center-list"
        :data-source="filteredTasks"
        :loading="taskLoading"
        :locale="{ emptyText: '暂无符合条件的任务' }"
      >
        <template #renderItem="{ item }">
          <a-list-item class="task-center-item">
            <div class="task-item-content">
              <div class="task-item-heading">
                <strong>{{ taskTitle(item) }}</strong>
                <StatusTag :status="item.status" />
              </div>
              <p :class="['task-item-message', { 'task-item-message--error': item.status === 'error' }]">
                {{ taskDescription(item) }}
              </p>
              <span class="task-item-time">更新于 {{ formatDate(item.updated_at) }}</span>
            </div>
            <div class="task-item-actions">
              <div v-if="isActiveTask(item)" class="task-progress" :aria-label="`任务进度 ${item.progress || 0}%`">
                <a-progress :percent="item.progress || 0" :show-info="false" size="small" />
                <span>{{ item.progress || 0 }}%</span>
              </div>
              <a-button
                v-else-if="item.type === 'artifact_cleanup' && item.status === 'error'"
                type="link"
                size="small"
                :loading="retryingTaskId === item.id"
                @click="retryCleanup(item.id)"
              >重试清理</a-button>
              <a-popconfirm
                v-else-if="item.can_remove"
                title="从历史中移除这条任务记录？"
                ok-text="移除"
                cancel-text="取消"
                @confirm="removeTask(item.id)"
              >
                <a-button type="link" danger size="small" :loading="removingTaskId === item.id">从历史移除</a-button>
              </a-popconfirm>
            </div>
          </a-list-item>
        </template>
      </a-list>
    </a-drawer>

    <a-button
      v-if="route.path !== '/ai-assistant'"
      class="assistant-fab"
      type="primary"
      shape="circle"
      aria-label="打开 AI 助手"
      @click="openAssistant = true"
    >
      <RobotOutlined />
    </a-button>
    <a-drawer v-model:open="openAssistant" title="AI 助手" width="600" :body-style="{ padding: 0 }">
      <GlobalAiAssistant />
    </a-drawer>

    <a-modal
      v-model:open="passwordOpen"
      title="修改密码"
      ok-text="确认修改"
      cancel-text="取消"
      :confirm-loading="passwordLoading"
      @ok="changePassword"
    >
      <a-form layout="vertical" class="modal-form">
        <a-form-item label="当前密码" required><a-input-password v-model:value="passwordForm.oldPassword" autocomplete="current-password" /></a-form-item>
        <a-form-item label="新密码" required extra="至少 4 个字符"><a-input-password v-model:value="passwordForm.newPassword" autocomplete="new-password" /></a-form-item>
        <a-form-item label="确认新密码" required><a-input-password v-model:value="passwordForm.confirm" autocomplete="new-password" /></a-form-item>
      </a-form>
    </a-modal>
  </a-layout>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  BookOutlined,
  ClockCircleOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  DeploymentUnitOutlined,
  DownOutlined,
  ExperimentOutlined,
  MessageOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
} from "@ant-design/icons-vue";
import message from "ant-design-vue/es/message";
import { api } from "@/services/api";
import { useAuthStore } from "@/stores/auth";
import { useTaskStore } from "@/stores/tasks";
import { formatDate, roleText, taskTypeText } from "@/utils/format";
import type { TaskRecord } from "@/types";
import GlobalAiAssistant from "@/components/ai/GlobalAiAssistant.vue";
import StatusTag from "@/components/StatusTag.vue";

type TaskFilter = "all" | "active" | "terminal";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const taskStore = useTaskStore();
const terminalStatuses = new Set(["success", "error", "cancelled", "skipped"]);
const openTasks = ref(false);
const openAssistant = ref(false);
const taskLoading = ref(false);
const clearingTasks = ref(false);
const removingTaskId = ref<number | null>(null);
const retryingTaskId = ref<number | null>(null);
const taskFilter = ref<TaskFilter>("all");
const passwordOpen = ref(false);
const passwordLoading = ref(false);
const passwordForm = reactive({ oldPassword: "", newPassword: "", confirm: "" });
const taskFilterOptions = [
  { label: "全部", value: "all" },
  { label: "进行中", value: "active" },
  { label: "已结束", value: "terminal" },
];

const activeKey = computed(() => {
  if (route.path.startsWith("/datasets")) return "/datasets";
  return route.path;
});
const currentPageTitle = computed(() => String(route.meta.title || "研究工作台"));
const accountInitial = computed(() => (auth.user?.username || "U").slice(0, 1).toUpperCase());
const hasTerminalTasks = computed(() => taskStore.recent.some((task) => terminalStatuses.has(task.status)));
const filteredTasks = computed(() => {
  if (taskFilter.value === "active") return taskStore.recent.filter(isActiveTask);
  if (taskFilter.value === "terminal") return taskStore.recent.filter((task) => terminalStatuses.has(task.status));
  return taskStore.recent;
});

function onMenuClick(event: { key: string }) {
  void router.push(event.key);
}

function isActiveTask(task: TaskRecord) {
  return ["pending", "running"].includes(task.status);
}

function taskTitle(task: TaskRecord) {
  return `${taskTypeText(task.type)}${task.dataset_name ? ` · ${task.dataset_name}` : ""}`;
}

function taskDescription(task: TaskRecord) {
  return task.error || task.message || (isActiveTask(task) ? "任务正在等待进度更新" : "任务已结束");
}

async function refreshTasks() {
  taskLoading.value = true;
  try {
    await taskStore.refreshRecent();
  } catch (error) {
    message.error((error as Error).message);
  } finally {
    taskLoading.value = false;
  }
}

async function removeTask(taskId: number) {
  removingTaskId.value = taskId;
  try {
    await taskStore.removeTask(taskId);
    message.success("任务记录已从历史中移除");
  } catch (error) {
    message.error((error as Error).message);
  } finally {
    removingTaskId.value = null;
  }
}

async function clearTerminalTasks() {
  clearingTasks.value = true;
  try {
    const count = await taskStore.clearTerminalTasks();
    message.success(count ? `已从历史移除 ${count} 条任务记录` : "已结束记录已从历史移除");
  } catch (error) {
    message.error((error as Error).message);
  } finally {
    clearingTasks.value = false;
  }
}

async function retryCleanup(taskId: number) {
  retryingTaskId.value = taskId;
  try {
    await api.retryCleanupTask(taskId);
    message.success("已重新提交文件清理");
    await refreshTasks();
  } catch (error) {
    message.error((error as Error).message);
  } finally {
    retryingTaskId.value = null;
  }
}

async function logout() {
  taskStore.stopActivePolling();
  try {
    await auth.logout();
    message.success("已安全退出");
    await router.replace("/login");
  } catch (error) {
    if (auth.authenticated) taskStore.startActivePolling();
    message.error((error as Error).message);
  }
}

async function changePassword() {
  if (!passwordForm.oldPassword) return message.warning("请输入当前密码");
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

watch(openTasks, (value) => {
  if (value) void refreshTasks();
});

watch(() => auth.authenticated, (authenticated) => {
  if (authenticated) {
    taskStore.startActivePolling();
    void taskStore.refreshRecent().catch(() => undefined);
  } else {
    taskStore.stopActivePolling();
  }
}, { immediate: true });

onBeforeUnmount(() => taskStore.stopActivePolling());
</script>

<style scoped>
.assistant-fab {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 50;
  width: 48px;
  height: 48px;
  box-shadow: 0 10px 24px rgba(31, 95, 169, 0.28);
}
</style>
