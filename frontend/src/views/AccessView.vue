<template>
  <PageHeader title="权限管理" description="查看自己的访问范围；管理员可维护账号，数据集所有者可在详情页配置共享成员。" />

  <div class="surface access-workbench">
    <a-tabs v-model:active-key="activeTab">
      <a-tab-pane key="datasets" tab="我的权限">
        <div class="tab-toolbar">
          <a-space wrap>
            <a-input-search v-model:value="datasetKeyword" allow-clear placeholder="搜索数据集" style="width: 240px" />
            <a-select v-model:value="roleFilter" style="width: 150px">
              <a-select-option value="">全部权限</a-select-option>
              <a-select-option value="owner">所有者</a-select-option>
              <a-select-option value="editor">编辑者</a-select-option>
              <a-select-option value="viewer">查看者</a-select-option>
              <a-select-option value="admin">平台管理员</a-select-option>
            </a-select>
          </a-space>
          <a-button :loading="datasetsLoading" @click="loadDatasets">刷新</a-button>
        </div>

        <a-table class="compact-table" size="small" :data-source="filteredDatasets" :columns="datasetColumns" row-key="id" :loading="datasetsLoading" :pagination="{ pageSize: 12 }" :locale="{ emptyText: '暂无可访问的数据集' }">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'name'">
              <a @click="$router.push(`/datasets/${record.id}`)">{{ record.name }}</a>
              <div class="muted compact-note">{{ record.description || "暂无描述" }}</div>
            </template>
            <template v-else-if="column.key === 'owner'">{{ record.owner_name || "待管理员认领" }}</template>
            <template v-else-if="column.key === 'visibility'">
              <a-tag :color="record.visibility === 'shared' ? 'blue' : 'default'">{{ record.visibility === "shared" ? "全员只读" : "私有" }}</a-tag>
            </template>
            <template v-else-if="column.key === 'role'">
              <a-tag :color="roleColor(record.effective_role)">{{ roleLabel(record.effective_role) }}</a-tag>
            </template>
            <template v-else-if="column.key === 'source'">{{ sourceLabel(record.permission_source) }}</template>
            <template v-else-if="column.key === 'actions'">
              <a-space>
                <a-button size="small" @click="$router.push(`/datasets/${record.id}`)">打开</a-button>
                <a-button v-if="record.can_manage" size="small" type="link" @click="$router.push(`/datasets/${record.id}?access=1`)">共享设置</a-button>
              </a-space>
            </template>
          </template>
        </a-table>
      </a-tab-pane>

      <a-tab-pane v-if="auth.isAdmin" key="users" tab="用户管理">
        <a-alert class="account-policy" type="info" show-icon message="账号采用停用策略" description="停用后账号将无法登录，但用户归属与审计记录会继续保留。" />
        <div class="tab-toolbar">
          <a-space wrap>
            <a-input-search v-model:value="userKeyword" allow-clear placeholder="搜索用户名" style="width: 220px" @search="loadUsers" />
            <a-select v-model:value="userRoleFilter" style="width: 130px" @change="loadUsers">
              <a-select-option value="">全部角色</a-select-option>
              <a-select-option value="admin">管理员</a-select-option>
              <a-select-option value="user">普通用户</a-select-option>
            </a-select>
            <a-select v-model:value="userStatusFilter" style="width: 130px" @change="loadUsers">
              <a-select-option value="">全部状态</a-select-option>
              <a-select-option value="enabled">已启用</a-select-option>
              <a-select-option value="disabled">已停用</a-select-option>
            </a-select>
          </a-space>
          <a-button type="primary" @click="createOpen = true">创建用户</a-button>
        </div>

        <a-table class="compact-table" size="small" :data-source="users" :columns="userColumns" row-key="id" :loading="usersLoading" :pagination="{ pageSize: 12 }" :locale="{ emptyText: '暂无用户记录' }">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'username'">
              <span>{{ record.username }}</span>
              <a-tag v-if="record.id === auth.user?.id" color="blue" style="margin-left: 8px">当前账号</a-tag>
            </template>
            <template v-else-if="column.key === 'role'">
              <a-select :value="record.role" size="small" style="width: 105px" @change="changeUserRole(record, $event)">
                <a-select-option value="user">普通用户</a-select-option>
                <a-select-option value="admin">管理员</a-select-option>
              </a-select>
            </template>
            <template v-else-if="column.key === 'enabled'">
              <a-switch :checked="record.is_enabled" :disabled="record.id === auth.user?.id" @change="changeUserEnabled(record, $event)" />
              <span class="switch-label">{{ record.is_enabled ? "已启用" : "已停用" }}</span>
            </template>
            <template v-else-if="column.key === 'owned'">{{ record.owned_dataset_count || 0 }}</template>
            <template v-else-if="column.key === 'ai'">
              <a-switch :checked="record.ai_enabled" @change="changeUserAiEnabled(record, $event)" />
              <span class="switch-label">{{ record.ai_enabled ? "已启用" : "已停用" }}</span>
            </template>
            <template v-else-if="column.key === 'aiLimit'">
              <a-input-number
                :value="record.ai_daily_limit_override"
                :min="0"
                :max="100000"
                size="small"
                placeholder="继承全局"
                style="width: 110px"
                @change="changeUserAiLimit(record, $event)"
              />
            </template>
            <template v-else-if="column.key === 'created'">{{ formatDate(record.created_at) }}</template>
            <template v-else-if="column.key === 'actions'">
              <a-button size="small" @click="openReset(record)">重置密码</a-button>
            </template>
          </template>
        </a-table>
      </a-tab-pane>

      <a-tab-pane v-if="auth.isAdmin" key="ai-models" tab="AI 模型">
        <AiAdminSettings />
      </a-tab-pane>

      <a-tab-pane key="audit" tab="审计日志">
        <div class="tab-toolbar">
          <a-space wrap>
            <a-select v-model:value="auditDatasetId" allow-clear placeholder="全部可管理数据集" style="width: 220px" @change="loadAudit">
              <a-select-option v-for="dataset in manageableDatasets" :key="dataset.id" :value="dataset.id">{{ dataset.name }}</a-select-option>
            </a-select>
            <a-select v-model:value="auditEvent" allow-clear placeholder="全部事件" style="width: 210px" @change="loadAudit">
              <a-select-option v-for="item in auditEventOptions" :key="item" :value="item">{{ eventLabel(item) }}</a-select-option>
            </a-select>
            <a-select v-model:value="auditActorId" allow-clear show-search option-filter-prop="label" placeholder="全部操作者" style="width: 170px" @change="loadAudit">
              <a-select-option v-for="user in users" :key="user.id" :value="user.id" :label="user.username">{{ user.username }}</a-select-option>
            </a-select>
            <a-range-picker v-model:value="auditDateRange" @change="loadAudit" />
          </a-space>
          <a-button :loading="auditLoading" @click="loadAudit">刷新</a-button>
        </div>

        <a-empty v-if="!auditLoading && !auditEvents.length" description="暂无可查看的审计记录" />
        <a-timeline v-else class="audit-timeline">
          <a-timeline-item v-for="item in auditEvents" :key="item.id">
            <div class="audit-head">
              <strong>{{ eventLabel(item.event) }}</strong>
              <span class="muted">{{ formatDate(item.created_at) }}</span>
            </div>
            <div class="audit-meta">
              操作者：{{ item.actor_name || "未知/匿名" }}
              <span v-if="item.target_user_name"> · 目标用户：{{ item.target_user_name }}</span>
              <span v-if="item.dataset_id"> · 数据集：{{ auditDatasetName(item.dataset_id) }}</span>
              <span v-if="auth.isAdmin && item.ip_address"> · IP {{ item.ip_address }}</span>
            </div>
            <div v-if="auditSummary(item)" class="audit-summary">{{ auditSummary(item) }}</div>
            <a-collapse v-if="Object.keys(item.details || {}).length" ghost class="audit-technical">
              <a-collapse-panel key="details" header="技术详情">
                <pre>{{ JSON.stringify(item.details, null, 2) }}</pre>
              </a-collapse-panel>
            </a-collapse>
          </a-timeline-item>
        </a-timeline>
      </a-tab-pane>
    </a-tabs>
  </div>

  <a-modal v-model:open="createOpen" title="创建用户" ok-text="创建" :confirm-loading="modalLoading" @ok="createUser">
    <a-form layout="vertical">
      <a-form-item label="用户名"><a-input v-model:value="createForm.username" autocomplete="off" /></a-form-item>
      <a-form-item label="初始密码"><a-input-password v-model:value="createForm.password" autocomplete="new-password" /></a-form-item>
      <a-form-item label="系统角色">
        <a-select v-model:value="createForm.role"><a-select-option value="user">普通用户</a-select-option><a-select-option value="admin">管理员</a-select-option></a-select>
      </a-form-item>
    </a-form>
  </a-modal>

  <a-modal v-model:open="resetOpen" :title="`重置 ${resetTarget?.username || ''} 的密码`" ok-text="确认重置" :confirm-loading="modalLoading" @ok="resetPassword">
    <a-alert type="warning" show-icon message="重置后旧密码立即失效，不会向任何页面返回密码明文。" style="margin-bottom: 16px" />
    <a-input-password v-model:value="resetPasswordValue" placeholder="输入新密码（至少 4 位）" autocomplete="new-password" />
  </a-modal>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { message, Modal } from "ant-design-vue";
import PageHeader from "@/components/PageHeader.vue";
import AiAdminSettings from "@/components/ai/AiAdminSettings.vue";
import { api } from "@/services/api";
import { useAuthStore } from "@/stores/auth";
import { formatDate, roleText, statusText, taskTypeText, visibilityText } from "@/utils/format";
import type { AuditEvent, Dataset, EffectiveRole, ManagedUser, PermissionSource } from "@/types";

const auth = useAuthStore();
const activeTab = ref("datasets");
const datasets = ref<Dataset[]>([]);
const users = ref<ManagedUser[]>([]);
const auditEvents = ref<AuditEvent[]>([]);
const datasetsLoading = ref(false);
const usersLoading = ref(false);
const auditLoading = ref(false);
const modalLoading = ref(false);
const datasetKeyword = ref("");
const roleFilter = ref("");
const userKeyword = ref("");
const userRoleFilter = ref("");
const userStatusFilter = ref("");
const auditDatasetId = ref<number | undefined>();
const auditEvent = ref<string | undefined>();
const auditActorId = ref<number | undefined>();
const auditDateRange = ref<Array<{ format: (pattern: string) => string }> | null>(null);
const createOpen = ref(false);
const resetOpen = ref(false);
const resetTarget = ref<ManagedUser | null>(null);
const resetPasswordValue = ref("");
const createForm = reactive({ username: "", password: "", role: "user" });

const datasetColumns = [
  { title: "数据集", key: "name" },
  { title: "所有者", key: "owner", width: 150 },
  { title: "可见性", key: "visibility", width: 130 },
  { title: "有效权限", key: "role", width: 130 },
  { title: "权限来源", key: "source", width: 140 },
  { title: "操作", key: "actions", width: 180 },
];
const userColumns = [
  { title: "用户名", key: "username" },
  { title: "角色", key: "role", width: 116 },
  { title: "状态", key: "enabled", width: 128 },
  { title: "拥有数据集", key: "owned", width: 100 },
  { title: "AI 权限", key: "ai", width: 112 },
  { title: "AI 每日限额", key: "aiLimit", width: 124 },
  { title: "创建时间", key: "created", width: 150 },
  { title: "操作", key: "actions", width: 102 },
];
const auditEventOptions = [
  "auth.login_failed", "user.created", "user.updated", "user.password_reset",
  "dataset.uploaded", "dataset.visibility_changed", "dataset.permission_added",
  "dataset.permission_updated", "dataset.permission_removed", "dataset.owner_transferred",
  "dataset.deleted", "dataset.process_submitted", "index.build_submitted",
  "index.deleted", "index_experiment.created", "index_experiment.finalized", "index_experiment.history_hidden",
  "index_evaluation.history_hidden", "joint_index.build_submitted", "joint_index.deleted",
  "task.history_hidden", "task.history_cleared", "ai.knowledge_deleted", "ai.conversation_deleted",
  "ai.provider_created", "ai.provider_key_rotated", "ai.model_tested", "ai.run_created", "ai.run_completed", "ai.run_failed",
];

const filteredDatasets = computed(() => datasets.value.filter((dataset) => {
  const matchesKeyword = !datasetKeyword.value || `${dataset.name} ${dataset.description || ""}`.toLowerCase().includes(datasetKeyword.value.toLowerCase());
  return matchesKeyword && (!roleFilter.value || dataset.effective_role === roleFilter.value);
}));
const manageableDatasets = computed(() => datasets.value.filter((dataset) => dataset.can_manage));

function roleLabel(role: EffectiveRole | null) {
  return ({ admin: "平台管理员", owner: "所有者", editor: "编辑者", viewer: "查看者" } as Record<string, string>)[role || ""] || "无权限";
}
function roleColor(role: EffectiveRole | null) {
  return ({ admin: "red", owner: "purple", editor: "green", viewer: "blue" } as Record<string, string>)[role || ""] || "default";
}
function sourceLabel(source: PermissionSource | null) {
  return ({ admin: "管理员覆盖", owner: "数据所有者", explicit: "成员授权", shared: "全员共享" } as Record<string, string>)[source || ""] || "-";
}
function eventLabel(event: string) {
  const labels: Record<string, string> = {
    "auth.login_failed": "登录失败", "auth.login_blocked": "停用账号登录被拦截", "auth.register": "用户注册",
    "auth.password_changed": "修改个人密码", "user.created": "管理员创建用户", "user.updated": "用户状态变更",
    "user.password_reset": "管理员重置密码", "dataset.uploaded": "上传数据集", "dataset.visibility_changed": "修改可见性",
    "dataset.permission_added": "新增成员权限", "dataset.permission_updated": "调整成员权限", "dataset.permission_removed": "移除成员权限",
    "dataset.owner_transferred": "转移所有权", "dataset.deleted": "删除数据集", "dataset.process_submitted": "提交数据处理",
    "index.build_submitted": "提交索引构建", "index.evaluation_submitted": "提交索引评估", "index.evaluated": "完成同步评估",
    "index.deleted": "删除索引", "index_experiment.history_hidden": "从历史移除索引实验", "index_evaluation.history_hidden": "从历史移除索引评估",
    "index_experiment.created": "创建索引实验", "index_experiment.finalized": "完成索引选优", "index_experiment.discarded": "放弃索引实验",
    "index_experiment.cleanup_retried": "重试实验清理", "joint_index.build_submitted": "提交联合索引构建", "joint_index.deleted": "删除联合索引",
    "task.history_hidden": "从历史移除任务", "task.history_cleared": "批量移除任务历史",
    "ai.knowledge_deleted": "删除知识资料", "ai.conversation_deleted": "删除 AI 会话",
    "ai.provider_created": "创建 AI 供应商", "ai.provider_updated": "更新 AI 供应商", "ai.provider_key_rotated": "替换 AI 密钥",
    "ai.provider_deleted": "删除 AI 供应商", "ai.model_created": "创建 AI 模型", "ai.model_updated": "更新 AI 模型",
    "ai.model_tested": "测试 AI 模型", "ai.run_created": "创建 AI 分析", "ai.run_approved": "确认 AI 检索",
    "ai.run_rejected": "拒绝 AI 检索", "ai.run_completed": "完成 AI 分析", "ai.run_failed": "AI 分析失败",
  };
  return labels[event] || "其他平台操作";
}

function auditDatasetName(datasetId: number) {
  return datasets.value.find((dataset) => dataset.id === datasetId)?.name || "受控数据集";
}

function auditSummary(item: AuditEvent) {
  const fieldLabels: Record<string, string> = {
    username: "用户名",
    name: "名称",
    role: "角色",
    old_role: "原角色",
    new_role: "新角色",
    visibility: "可见性",
    old_visibility: "原可见性",
    level: "权限级别",
    old_level: "原权限级别",
    is_enabled: "账号状态",
    ai_enabled: "AI 权限",
    enabled: "启用状态",
    is_default: "默认模型",
    provider: "供应商",
    status: "状态",
    type: "任务类型",
    scope: "知识空间",
    count: "记录数量",
    success: "测试结果",
    latency_ms: "响应耗时",
  };
  const roleFields = new Set(["role", "old_role", "new_role"]);
  const visibilityFields = new Set(["visibility", "old_visibility"]);
  const entries = Object.entries(item.details || {})
    .filter(([key, value]) => fieldLabels[key] && value !== null && value !== undefined)
    .slice(0, 4)
    .map(([key, value]) => {
      let display = String(value);
      if (typeof value === "boolean") display = value ? "是" : "否";
      if (roleFields.has(key)) display = ({ admin: "管理员", user: "普通用户", owner: "所有者", editor: "编辑者", viewer: "查看者" } as Record<string, string>)[String(value)] || roleText(String(value));
      if (visibilityFields.has(key)) display = visibilityText(String(value));
      if (key === "status") display = statusText(String(value));
      if (key === "type") display = taskTypeText(String(value));
      if (key === "scope") display = ({ platform: "平台知识", dataset: "数据集知识", personal: "个人知识" } as Record<string, string>)[String(value)] || "知识资料";
      if (key === "is_enabled" || key === "enabled") display = Boolean(value) ? "已启用" : "已停用";
      if (key === "latency_ms") display = `${value} ms`;
      return `${fieldLabels[key]}：${display}`;
    });
  return entries.join(" · ");
}

async function loadDatasets() {
  datasetsLoading.value = true;
  try { datasets.value = (await api.accessDatasets()).datasets; }
  catch (error) { message.error((error as Error).message); }
  finally { datasetsLoading.value = false; }
}
async function loadUsers() {
  if (!auth.isAdmin && !manageableDatasets.value.length) return;
  usersLoading.value = true;
  try { users.value = (await api.accessUsers(userKeyword.value, auth.isAdmin ? userRoleFilter.value : "", auth.isAdmin ? userStatusFilter.value : "")).users; }
  catch (error) { message.error((error as Error).message); }
  finally { usersLoading.value = false; }
}
async function loadAudit() {
  auditLoading.value = true;
  try {
    auditEvents.value = (await api.auditEvents({
      datasetId: auditDatasetId.value,
      actorId: auditActorId.value,
      event: auditEvent.value,
      from: auditDateRange.value?.[0]?.format("YYYY-MM-DD"),
      to: auditDateRange.value?.[1]?.format("YYYY-MM-DD"),
    })).events;
  }
  catch (error) { message.error((error as Error).message); }
  finally { auditLoading.value = false; }
}
async function createUser() {
  if (!createForm.username || createForm.password.length < 4) return message.warning("请输入用户名和至少 4 位密码");
  modalLoading.value = true;
  try {
    await api.createUser(createForm);
    message.success("用户已创建");
    createOpen.value = false;
    Object.assign(createForm, { username: "", password: "", role: "user" });
    await loadUsers();
  } catch (error) { message.error((error as Error).message); }
  finally { modalLoading.value = false; }
}
function updateUser(record: ManagedUser, patch: { role?: string; is_enabled?: boolean; ai_enabled?: boolean; ai_daily_limit_override?: number | "" }) {
  const action = async () => {
    try {
      const updated = (await api.updateUser(record.id, patch)).user;
      Object.assign(record, updated);
      if (record.id === auth.user?.id) Object.assign(auth.user, updated);
      message.success("用户状态已更新");
      await loadAudit();
    } catch (error) { message.error((error as Error).message); await loadUsers(); }
  };
  if (patch.is_enabled === false || (record.role === "admin" && patch.role === "user")) {
    Modal.confirm({ title: "确认调整高权限账号？", content: "停用或降级后，该用户将无法继续使用管理员能力。", okText: "确认", cancelText: "取消", onOk: action, onCancel: loadUsers });
  } else action();
}
function changeUserRole(record: ManagedUser, value: unknown) { updateUser(record, { role: String(value) }); }
function changeUserEnabled(record: ManagedUser, value: unknown) { updateUser(record, { is_enabled: Boolean(value) }); }
function changeUserAiEnabled(record: ManagedUser, value: unknown) { updateUser(record, { ai_enabled: Boolean(value) }); }
function changeUserAiLimit(record: ManagedUser, value: unknown) {
  updateUser(record, { ai_daily_limit_override: value === null || value === undefined ? "" : Number(value) });
}
function openReset(record: ManagedUser) {
  resetTarget.value = record;
  resetPasswordValue.value = "";
  resetOpen.value = true;
}
async function resetPassword() {
  if (!resetTarget.value || resetPasswordValue.value.length < 4) return message.warning("密码至少 4 位");
  modalLoading.value = true;
  try { await api.resetUserPassword(resetTarget.value.id, resetPasswordValue.value); message.success("密码已重置"); resetOpen.value = false; }
  catch (error) { message.error((error as Error).message); }
  finally { modalLoading.value = false; }
}

watch(activeTab, (tab) => { if (tab === "users") loadUsers(); if (tab === "audit") loadAudit(); });
onMounted(async () => { await loadDatasets(); if (auth.isAdmin || manageableDatasets.value.length) await loadUsers(); await loadAudit(); });
</script>

<style scoped>
.access-workbench { padding: 0 20px 20px; }
.account-policy { margin: 4px 0 10px; }
.tab-toolbar { min-height: 56px; display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.compact-note { margin-top: 3px; max-width: 420px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.switch-label { margin-left: 8px; color: #64748b; }
.audit-timeline { margin-top: 20px; padding: 4px 10px; }
.audit-head { display: flex; justify-content: space-between; gap: 16px; }
.audit-meta { color: #64748b; font-size: 13px; margin-top: 4px; }
.audit-summary { margin-top: 7px; color: #536278; font-size: 12px; }
.audit-technical { width: fit-content; max-width: 100%; margin-top: 3px; }
.audit-technical :deep(.ant-collapse-header) { padding: 4px 0 !important; color: #7d899a !important; font-size: 11px; }
.audit-technical :deep(.ant-collapse-content-box) { padding: 0 !important; }
.audit-technical pre { max-width: 760px; max-height: 220px; margin: 0; padding: 10px 12px; overflow: auto; border: 1px solid #e4e9ef; border-radius: 7px; background: #f8fafc; color: #4c5b70; font-size: 11px; line-height: 1.55; white-space: pre-wrap; word-break: break-word; }
</style>
