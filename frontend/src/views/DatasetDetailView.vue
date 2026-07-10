<template>
  <PageHeader :title="dataset?.name || '数据集详情'" :description="dataset?.description || '数据集资源详情、可视化、索引和任务记录。'">
    <template #actions>
      <a-space>
        <a-button @click="$router.push('/datasets')">返回列表</a-button>
        <a-tag v-if="dataset" :color="accessRoleColor(dataset.effective_role)">{{ accessRoleLabel(dataset.effective_role) }}</a-tag>
        <a-button v-if="dataset?.can_manage" @click="openAccess">共享设置</a-button>
        <a-button v-if="dataset?.can_edit && (dataset.status === 'uploaded' || dataset.status === 'error')" type="primary" :loading="actionLoading" @click="process">处理数据集</a-button>
        <a-button v-if="dataset?.can_edit && ['processed', 'indexed'].includes(dataset.status)" type="primary" @click="$router.push(`/index-lab?dataset=${dataset.id}`)">构建索引</a-button>
        <a-button v-if="dataset?.ready_index_count" @click="$router.push(`/query-lab?dataset=${dataset.id}`)">检索细胞</a-button>
      </a-space>
    </template>
  </PageHeader>

  <a-spin :spinning="store.loading">
    <template v-if="dataset">
      <div class="metric-grid">
        <div class="metric-tile"><div class="metric-label">细胞数</div><div class="metric-value">{{ numberOrDash(dataset.n_cells) }}</div></div>
        <div class="metric-tile"><div class="metric-label">基因数</div><div class="metric-value">{{ numberOrDash(dataset.n_genes) }}</div></div>
        <div class="metric-tile"><div class="metric-label">PCA 维度</div><div class="metric-value">{{ numberOrDash(dataset.vector_dim) }}</div></div>
        <div class="metric-tile"><div class="metric-label">可用索引</div><div class="metric-value">{{ dataset.ready_index_count }}</div></div>
      </div>

      <div v-if="currentTask" class="surface surface-pad" style="margin-bottom: 18px">
        <div class="panel-title">当前任务</div>
        <a-alert
          :message="currentTask.message || '任务执行中...'"
          :description="currentTask.status === 'error' ? currentTask.error : undefined"
          :type="currentTask.status === 'error' ? 'error' : currentTask.status === 'success' ? 'success' : 'info'"
          show-icon
        />
        <a-progress style="margin-top: 12px" :percent="currentTask.progress || 0" :status="currentTask.status === 'error' ? 'exception' : currentTask.status === 'success' ? 'success' : 'active'" />
      </div>

      <div class="two-column">
        <div class="stack">
          <div class="surface surface-pad">
            <div class="panel-title">资源摘要</div>
            <a-descriptions :column="1" size="small" bordered>
              <a-descriptions-item label="状态"><StatusTag :status="dataset.status" /></a-descriptions-item>
              <a-descriptions-item label="访问范围">{{ dataset.owner_name || "待管理员认领" }} / {{ dataset.visibility === "shared" ? "全员只读" : "私有" }}</a-descriptions-item>
              <a-descriptions-item label="我的权限">{{ accessRoleLabel(dataset.effective_role) }}</a-descriptions-item>
              <a-descriptions-item label="创建时间">{{ formatDate(dataset.created_at) }}</a-descriptions-item>
              <a-descriptions-item v-if="dataset.error_message" label="错误信息">{{ dataset.error_message }}</a-descriptions-item>
            </a-descriptions>
          </div>

          <div class="surface">
            <div class="toolbar"><span class="toolbar-title">细胞统计</span></div>
            <div class="surface-pad">
              <a-tabs>
                <a-tab-pane key="cell_type" tab="细胞类型"><StatList :rows="stats.cell_type || []" /></a-tab-pane>
                <a-tab-pane key="disease" tab="疾病"><StatList :rows="stats.disease || []" /></a-tab-pane>
                <a-tab-pane key="age_group" tab="年龄组"><StatList :rows="stats.age_group || []" /></a-tab-pane>
              </a-tabs>
            </div>
          </div>

          <div class="surface">
            <div class="toolbar"><span class="toolbar-title">最近任务</span></div>
            <a-list :data-source="store.recentTasks" size="small">
              <template #renderItem="{ item }">
                <a-list-item>
                  <a-list-item-meta :title="taskTypeText(item.type)" :description="item.message || item.error || '-'">
                    <template #avatar><StatusTag :status="item.status" /></template>
                  </a-list-item-meta>
                </a-list-item>
              </template>
            </a-list>
          </div>
        </div>

        <div class="stack">
          <div class="surface">
            <div class="toolbar">
              <span class="toolbar-title">嵌入图</span>
              <a-button size="small" :disabled="!canPlot" :loading="plotLoading" @click="loadScatter">重新加载</a-button>
            </div>
            <div class="surface-pad">
              <a-alert v-if="plotError" style="margin-bottom: 12px" type="error" show-icon :message="plotError" />
              <PlotlyPanel v-if="scatter" :payload="scatter" :interactive="true" :height="560" />
              <div v-else class="placeholder-panel">{{ canPlot ? "加载细胞分布图" : "处理数据集后可查看 UMAP/PCA 分布" }}</div>
            </div>
          </div>

          <div class="surface">
            <div class="toolbar">
              <span class="toolbar-title">索引</span>
              <a-button v-if="dataset.can_edit" size="small" type="primary" :disabled="!['processed', 'indexed'].includes(dataset.status)" @click="$router.push(`/index-lab?dataset=${dataset.id}`)">索引实验室</a-button>
            </div>
            <a-table :data-source="dataset.indexes" :columns="indexColumns" row-key="id" size="small" :pagination="false">
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'status'"><StatusTag :status="record.status" /></template>
              </template>
            </a-table>
          </div>
        </div>
      </div>
    </template>
  </a-spin>

  <a-drawer v-model:open="accessOpen" title="共享设置" width="520" :destroy-on-close="false">
    <a-spin :spinning="accessLoading">
      <template v-if="accessConfig">
        <a-alert
          :type="accessConfig.visibility === 'shared' ? 'info' : 'success'"
          show-icon
          :message="accessConfig.visibility === 'shared' ? '全员只读' : '仅成员可见'"
          :description="accessConfig.visibility === 'shared' ? '所有登录用户拥有 Viewer 权限；显式 Editor 仍可处理数据和运行索引实验。' : '只有 Owner、Admin 和下方明确授权的成员可以访问。'"
          style="margin-bottom: 18px"
        />

        <a-descriptions :column="1" bordered size="small" style="margin-bottom: 18px">
          <a-descriptions-item label="所有者">{{ accessConfig.owner?.username || "待管理员认领" }}</a-descriptions-item>
          <a-descriptions-item label="可见性">
            <a-radio-group :value="accessConfig.visibility" button-style="solid" :disabled="accessSaving" @change="changeVisibility">
              <a-radio-button value="private">私有</a-radio-button>
              <a-radio-button value="shared">全员只读</a-radio-button>
            </a-radio-group>
          </a-descriptions-item>
        </a-descriptions>

        <div class="panel-title">添加成员</div>
        <div class="member-add-row">
          <a-select
            v-model:value="selectedUserId"
            show-search
            allow-clear
            :filter-option="false"
            placeholder="输入用户名搜索"
            style="flex: 1"
            :options="userOptions"
            :loading="userSearching"
            @search="searchUsers"
          />
          <a-select v-model:value="selectedLevel" style="width: 112px"><a-select-option value="viewer">Viewer</a-select-option><a-select-option value="editor">Editor</a-select-option></a-select>
          <a-button type="primary" :disabled="!selectedUserId" :loading="accessSaving" @click="savePermission">添加</a-button>
        </div>

        <a-table :data-source="accessConfig.permissions" :columns="permissionColumns" row-key="id" size="small" :pagination="false" style="margin-top: 14px">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'user'">
              {{ record.username }}
              <a-tag v-if="!record.user_enabled" color="default">已停用</a-tag>
            </template>
            <template v-else-if="column.key === 'level'">
              <a-select :value="record.level" size="small" style="width: 105px" :disabled="!record.user_enabled" @change="updatePermission(record.user_id, $event)">
                <a-select-option value="viewer">Viewer</a-select-option><a-select-option value="editor">Editor</a-select-option>
              </a-select>
            </template>
            <template v-else-if="column.key === 'actions'"><a-button danger type="link" size="small" @click="removePermission(record.user_id, record.username)">移除</a-button></template>
          </template>
        </a-table>

        <a-divider />
        <div class="panel-title">转移所有权</div>
        <a-alert type="warning" show-icon message="转移后你将自动保留 Editor 权限，新的 Owner 可以修改共享设置或删除数据集。" style="margin-bottom: 12px" />
        <div class="member-add-row">
          <a-select v-model:value="transferUserId" show-search allow-clear :filter-option="false" placeholder="搜索新的所有者" style="flex: 1" :options="userOptions" :loading="userSearching" @search="searchUsers" />
          <a-button danger :disabled="!transferUserId" :loading="accessSaving" @click="transferOwnership">确认转移</a-button>
        </div>
      </template>
    </a-spin>
  </a-drawer>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { message, Modal } from "ant-design-vue";
import PageHeader from "@/components/PageHeader.vue";
import PlotlyPanel from "@/components/PlotlyPanel.vue";
import StatusTag from "@/components/StatusTag.vue";
import { api } from "@/services/api";
import { useDatasetStore } from "@/stores/datasets";
import { useTaskStore } from "@/stores/tasks";
import { formatDate, numberOrDash, taskTypeText } from "@/utils/format";
import type { DatasetAccess, EffectiveRole, ManagedUser, PlotlyPayload, TaskRecord } from "@/types";

const route = useRoute();
const store = useDatasetStore();
const taskStore = useTaskStore();
const actionLoading = ref(false);
const plotLoading = ref(false);
const plotError = ref("");
const currentTask = ref<TaskRecord | null>(null);
const scatter = ref<PlotlyPayload | null>(null);
const accessOpen = ref(false);
const accessLoading = ref(false);
const accessSaving = ref(false);
const accessConfig = ref<DatasetAccess | null>(null);
const userSearching = ref(false);
const userResults = ref<ManagedUser[]>([]);
const selectedUserId = ref<number | undefined>();
const selectedLevel = ref<"viewer" | "editor">("viewer");
const transferUserId = ref<number | undefined>();
const datasetId = computed(() => Number(route.params.id));
const dataset = computed(() => store.current);
const stats = computed(() => store.stats);
const canPlot = computed(() => !!dataset.value && ["processed", "indexed"].includes(dataset.value.status));
const userOptions = computed(() => userResults.value
  .filter((user) => user.is_enabled && user.id !== accessConfig.value?.owner?.id)
  .map((user) => ({ value: user.id, label: `${user.username}${user.role === "admin" ? " · Admin" : ""}` })));

const indexColumns = [
  { title: "算法", dataIndex: "algorithm", width: 110 },
  { title: "距离度量", dataIndex: "metric", width: 90 },
  { title: "M", dataIndex: "M", width: 70 },
  { title: "ef", dataIndex: "ef_search", width: 80 },
  { title: "构建耗时 ms", dataIndex: "build_time_ms", width: 120 },
  { title: "状态", key: "status", width: 100 },
];
const permissionColumns = [
  { title: "成员", key: "user" },
  { title: "权限", key: "level", width: 125 },
  { title: "操作", key: "actions", width: 80 },
];

function accessRoleLabel(role: EffectiveRole | null | undefined) {
  return ({ admin: "Admin", owner: "Owner", editor: "Editor", viewer: "Viewer" } as Record<string, string>)[role || ""] || "无权限";
}

function accessRoleColor(role: EffectiveRole | null | undefined) {
  return ({ admin: "red", owner: "purple", editor: "green", viewer: "blue" } as Record<string, string>)[role || ""] || "default";
}

const StatList = defineComponent({
  props: { rows: { type: Array, required: true } },
  setup(props) {
    return () => {
      const rows = props.rows as { name: string; count: number }[];
      if (!rows.length) return h("div", { class: "muted" }, "暂无统计数据");
      const max = Math.max(...rows.map((row) => row.count), 1);
      return h("div", { class: "stack" }, rows.slice(0, 10).map((row) =>
        h("div", { style: "display:grid;grid-template-columns:150px 1fr 64px;gap:10px;align-items:center;font-size:13px;" }, [
          h("span", { title: row.name, style: "overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" }, row.name),
          h("div", { style: "height:8px;background:#e8eef6;border-radius:999px;overflow:hidden;" }, [
            h("div", { style: `width:${Math.round((row.count / max) * 100)}%;height:100%;background:#2563eb;` }),
          ]),
          h("span", { class: "muted", style: "text-align:right;" }, row.count),
        ]),
      ));
    };
  },
});

async function reload() {
  await store.loadDetail(datasetId.value);
  if (canPlot.value) loadScatter();
}

async function loadScatter() {
  if (!canPlot.value) return;
  plotLoading.value = true;
  plotError.value = "";
  try {
    const data = await api.scatter(datasetId.value);
    scatter.value = data.scatter_plot;
  } catch (error) {
    plotError.value = (error as Error).message;
    message.error(plotError.value);
  } finally {
    plotLoading.value = false;
  }
}

async function process() {
  actionLoading.value = true;
  currentTask.value = null;
  try {
    const data = await api.processDataset(datasetId.value);
    await taskStore.waitForTask(data.task_id, (task) => {
      currentTask.value = task;
    });
    message.success("数据集处理完成");
    await reload();
  } catch (error) {
    message.error((error as Error).message);
  } finally {
    actionLoading.value = false;
  }
}

async function openAccess() {
  accessOpen.value = true;
  accessLoading.value = true;
  try {
    accessConfig.value = (await api.datasetAccess(datasetId.value)).access;
    await searchUsers("");
  } catch (error) {
    message.error((error as Error).message);
    accessOpen.value = false;
  } finally {
    accessLoading.value = false;
  }
}

async function searchUsers(keyword: string) {
  userSearching.value = true;
  try { userResults.value = (await api.accessUsers(keyword)).users; }
  catch (error) { message.error((error as Error).message); }
  finally { userSearching.value = false; }
}

function changeVisibility(event: { target: { value: "private" | "shared" } }) {
  if (!accessConfig.value || event.target.value === accessConfig.value.visibility) return;
  const visibility = event.target.value;
  const apply = async () => {
    accessSaving.value = true;
    try {
      accessConfig.value = (await api.updateDatasetVisibility(datasetId.value, visibility)).access;
      message.success("可见性已更新");
      await reload();
    } catch (error) { message.error((error as Error).message); }
    finally { accessSaving.value = false; }
  };
  if (visibility === "shared") {
    Modal.confirm({ title: "设为全员只读？", content: "所有登录用户都将能够查看和检索此数据集，但不能处理数据或修改索引。", okText: "确认共享", cancelText: "取消", onOk: apply });
  } else apply();
}

async function savePermission() {
  if (!selectedUserId.value) return;
  await updatePermission(selectedUserId.value, selectedLevel.value);
  selectedUserId.value = undefined;
}

async function updatePermission(userId: number, level: unknown) {
  if (level !== "viewer" && level !== "editor") return;
  accessSaving.value = true;
  try {
    await api.saveDatasetPermission(datasetId.value, userId, level);
    accessConfig.value = (await api.datasetAccess(datasetId.value)).access;
    message.success("成员权限已保存");
  } catch (error) { message.error((error as Error).message); }
  finally { accessSaving.value = false; }
}

function removePermission(userId: number, username: string) {
  Modal.confirm({
    title: `移除 ${username} 的权限？`,
    content: accessConfig.value?.visibility === "shared" ? "显式权限将被移除；由于数据集当前全员共享，该用户仍保留 Viewer 权限。" : "移除后该用户将无法继续访问此数据集。",
    okText: "移除", okType: "danger", cancelText: "取消",
    async onOk() {
      accessSaving.value = true;
      try { await api.removeDatasetPermission(datasetId.value, userId); accessConfig.value = (await api.datasetAccess(datasetId.value)).access; message.success("成员已移除"); }
      catch (error) { message.error((error as Error).message); }
      finally { accessSaving.value = false; }
    },
  });
}

function transferOwnership() {
  if (!transferUserId.value) return;
  const target = userResults.value.find((user) => user.id === transferUserId.value);
  Modal.confirm({
    title: `将所有权转移给 ${target?.username || "所选用户"}？`,
    content: "转移立即生效；你会保留 Editor 权限，但不能再管理共享设置或删除数据集。",
    okText: "确认转移", okType: "danger", cancelText: "取消",
    async onOk() {
      accessSaving.value = true;
      try {
        await api.transferDatasetOwnership(datasetId.value, transferUserId.value!);
        message.success("所有权已转移");
        accessOpen.value = false;
        await reload();
      } catch (error) { message.error((error as Error).message); }
      finally { accessSaving.value = false; }
    },
  });
}

onMounted(async () => {
  await reload();
  if (route.query.access === "1" && dataset.value?.can_manage) openAccess();
});
</script>

<style scoped>
.member-add-row { display: flex; align-items: center; gap: 10px; }
@media (max-width: 620px) { .member-add-row { align-items: stretch; flex-direction: column; } }
</style>
