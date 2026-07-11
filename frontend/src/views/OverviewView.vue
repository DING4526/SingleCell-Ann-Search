<template>
  <PageHeader title="概览" description="集中查看数据资源、索引、检索与后台任务的实时状态。">
    <template #actions>
      <a-space>
        <a-button :loading="loading" @click="reload"><ReloadOutlined />刷新</a-button>
        <a-button type="primary" @click="$router.push('/datasets')"><DatabaseOutlined />管理数据资源</a-button>
      </a-space>
    </template>
  </PageHeader>

  <ErrorState v-if="loadError" :description="loadError" @retry="reload" />
  <template v-else>
    <a-skeleton v-if="loading && !hasSummary" active :paragraph="{ rows: 8 }" />
    <template v-else>
      <div class="metric-grid overview-metrics">
        <MetricCard label="数据资源" :value="formatCount(datasetTotal)" :hint="`${readyDatasetTotal} 个已就绪`">
          <template #icon><DatabaseOutlined /></template>
        </MetricCard>
        <MetricCard label="资源健康" :value="`${resourceHealth}%`" :hint="datasetTotal ? '按已处理和已索引资源计算' : '尚未导入数据'" :tone="resourceHealth >= 80 ? 'positive' : 'default'">
          <template #icon><CheckCircleOutlined /></template>
        </MetricCard>
        <MetricCard label="可用索引" :value="formatCount(indexTotal)" hint="可直接用于检索" :tone="indexTotal ? 'positive' : 'warning'">
          <template #icon><ApartmentOutlined /></template>
        </MetricCard>
        <MetricCard label="累计检索" :value="formatCount(queryTotal)" hint="包含全部检索模式">
          <template #icon><SearchOutlined /></template>
        </MetricCard>
        <MetricCard label="进行中任务" :value="formatCount(activeTaskCount)" :hint="`异常任务 ${errorTaskCount} 项`" :tone="errorTaskCount ? 'danger' : activeTaskCount ? 'warning' : 'positive'">
          <template #icon><ClockCircleOutlined /></template>
        </MetricCard>
      </div>

      <section class="next-action surface">
        <div class="next-action__icon"><CompassOutlined /></div>
        <div class="next-action__copy">
          <span>下一步建议</span>
          <h2>{{ nextAction.title }}</h2>
          <p>{{ nextAction.description }}</p>
        </div>
        <a-button type="primary" @click="$router.push(nextAction.path)">
          {{ nextAction.label }}<ArrowRightOutlined />
        </a-button>
      </section>

      <div class="overview-grid">
        <section class="surface table-shell">
          <div class="toolbar">
            <div>
              <div class="toolbar-title">最近数据集</div>
              <div class="toolbar-description">近期创建或更新的数据资源</div>
            </div>
            <a-button size="small" @click="$router.push('/datasets')">查看全部</a-button>
          </div>
          <a-table
            class="compact-table"
            size="small"
            :pagination="false"
            :data-source="recentDatasets"
            :columns="datasetColumns"
            :locale="{ emptyText: '暂无数据集' }"
            row-key="id"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'name'">
                <div class="primary-cell">
                  <a @click="$router.push(`/datasets/${record.id}`)">{{ record.name }}</a>
                  <span>{{ record.created_at ? `创建于 ${formatDate(record.created_at)}` : '尚无时间信息' }}</span>
                </div>
              </template>
              <template v-else-if="column.key === 'status'"><StatusTag :status="record.status" /></template>
              <template v-else-if="column.key === 'n_cells'"><span class="numeric-cell">{{ numberOrDash(record.n_cells) }}</span></template>
            </template>
          </a-table>
        </section>

        <section class="surface">
          <div class="toolbar">
            <div>
              <div class="toolbar-title">最近任务</div>
              <div class="toolbar-description">处理、构建和检索任务的最新进度</div>
            </div>
            <span class="toolbar-meta">{{ recentTasks.length }} 项</span>
          </div>
          <a-list class="overview-task-list" :data-source="recentTasks" :locale="{ emptyText: '暂无任务记录' }">
            <template #renderItem="{ item }">
              <a-list-item>
                <a-list-item-meta>
                  <template #title>
                    <div class="overview-task-title">
                      <span>{{ taskTitle(item) }}</span>
                      <StatusTag :status="item.status" />
                    </div>
                  </template>
                  <template #description>
                    <div class="overview-task-description">
                      <span>{{ item.error || item.message || '任务状态已更新' }}</span>
                      <time>{{ formatDate(item.updated_at) }}</time>
                    </div>
                  </template>
                </a-list-item-meta>
              </a-list-item>
            </template>
          </a-list>
        </section>
      </div>
    </template>
  </template>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  ApartmentOutlined,
  ArrowRightOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  CompassOutlined,
  DatabaseOutlined,
  ReloadOutlined,
  SearchOutlined,
} from "@ant-design/icons-vue";
import { api } from "@/services/api";
import PageHeader from "@/components/PageHeader.vue";
import StatusTag from "@/components/StatusTag.vue";
import MetricCard from "@/components/MetricCard.vue";
import ErrorState from "@/components/ErrorState.vue";
import { formatDate, numberOrDash, taskTypeText } from "@/utils/format";
import type { TaskRecord } from "@/types";

type RecentDataset = {
  id: number;
  name: string;
  status: string;
  n_cells?: number | null;
  created_at?: string | null;
};

type DashboardSummary = Record<string, unknown> & {
  recent_datasets?: RecentDataset[];
  recent_tasks?: TaskRecord[];
};

const summary = ref<DashboardSummary>({});
const loading = ref(false);
const loadError = ref("");
const hasSummary = computed(() => Object.keys(summary.value).length > 0);
const recentDatasets = computed(() => Array.isArray(summary.value.recent_datasets) ? summary.value.recent_datasets : []);
const recentTasks = computed(() => Array.isArray(summary.value.recent_tasks) ? summary.value.recent_tasks : []);
const datasetTotal = computed(() => summaryCount(["datasets_total"]));
const uploadedDatasetTotal = computed(() => summaryCount(["datasets_uploaded"]));
const processedDatasetTotal = computed(() => summaryCount(["datasets_processed"]));
const indexedDatasetTotal = computed(() => summaryCount(["datasets_indexed"]));
const readyDatasetTotal = computed(() => processedDatasetTotal.value + indexedDatasetTotal.value);
const resourceHealth = computed(() => datasetTotal.value ? Math.round((readyDatasetTotal.value / datasetTotal.value) * 100) : 0);
const indexTotal = computed(() => summaryCount(["indexes_total", "ready_indexes"]));
const queryTotal = computed(() => summaryCount(["queries_total", "searches_total", "recent_queries"]));
const activeTaskCount = computed(() => summaryCount(
  ["tasks_active", "active_tasks", "active_task_count", "active_tasks_total", "running_tasks"],
  recentTasks.value.filter((task) => ["pending", "running"].includes(task.status)).length,
));
const errorTaskCount = computed(() => summaryCount(
  ["tasks_error", "failed_tasks", "error_task_count", "tasks_failed", "error_tasks"],
  recentTasks.value.filter((task) => task.status === "error").length,
));

const nextAction = computed(() => {
  const failedTask = recentTasks.value.find((task) => task.status === "error");
  if (errorTaskCount.value) {
    const relatedPath = failedTask?.dataset_id
      ? `/datasets/${failedTask.dataset_id}`
      : failedTask?.type === "build_joint_index" ? "/joint-indexes" : "/index-lab";
    return {
      title: "检查异常任务关联的数据资源",
      description: "最近有后台任务未能完成。打开相关资源可查看错误信息并重新执行。",
      label: "查看相关资源",
      path: relatedPath,
    };
  }
  if (!datasetTotal.value) {
    return {
      title: "导入首个单细胞数据集",
      description: "添加数据资源后，平台会引导完成预处理、索引构建和相似细胞检索。",
      label: "导入数据",
      path: "/datasets",
    };
  }
  if (uploadedDatasetTotal.value) {
    const datasetId = summaryNumber("first_uploaded_id");
    return {
      title: "处理待就绪的数据集",
      description: `当前有 ${uploadedDatasetTotal.value} 个已上传资源等待预处理。`,
      label: "打开待处理资源",
      path: datasetId ? `/datasets/${datasetId}` : "/datasets",
    };
  }
  if (processedDatasetTotal.value) {
    const datasetId = summaryNumber("first_processed_id");
    return {
      title: "为已处理数据构建索引",
      description: "通过索引实验室选择合适配置，完成后即可运行相似细胞检索。",
      label: "进入索引实验室",
      path: datasetId ? `/index-lab?dataset=${datasetId}` : "/index-lab",
    };
  }
  return {
    title: "开始一次相似细胞检索",
    description: `当前有 ${indexTotal.value} 个可用索引，可在单数据集、跨数据集或联合索引模式中运行检索。`,
    label: "进入检索实验室",
    path: "/query-lab",
  };
});

const datasetColumns = [
  { title: "数据集", dataIndex: "name", key: "name" },
  { title: "状态", dataIndex: "status", key: "status", width: 104 },
  { title: "细胞数", dataIndex: "n_cells", key: "n_cells", width: 100, align: "right" as const },
];

function summaryNumber(key: string) {
  const value = summary.value[key];
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function summaryCount(keys: string[], fallback = 0) {
  for (const key of keys) {
    const value = summary.value[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
  }
  return fallback;
}

function formatCount(value: number) {
  return value.toLocaleString("zh-CN");
}

function taskTitle(task: TaskRecord) {
  return `${taskTypeText(task.type)}${task.dataset_name ? ` · ${task.dataset_name}` : ""}`;
}

async function reload() {
  loading.value = true;
  loadError.value = "";
  try {
    summary.value = await api.dashboardSummary() as DashboardSummary;
  } catch (error) {
    loadError.value = (error as Error).message || "暂时无法获取概览数据。";
  } finally {
    loading.value = false;
  }
}

onMounted(reload);
</script>

<style scoped>
.overview-metrics {
  grid-template-columns: repeat(5, minmax(0, 1fr));
}

.next-action {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 16px;
  margin-bottom: 18px;
  padding: 18px 20px;
  background: linear-gradient(105deg, #f8fbff 0%, #ffffff 65%);
}

.next-action__icon {
  display: grid;
  width: 42px;
  height: 42px;
  place-items: center;
  border-radius: 10px;
  background: #e8f1fb;
  color: #1f5fa9;
  font-size: 20px;
}

.next-action__copy span {
  color: #1f5fa9;
  font-size: 12px;
  font-weight: 700;
}

.next-action__copy h2 {
  margin: 2px 0 3px;
  color: #17243a;
  font-size: 16px;
}

.next-action__copy p {
  margin: 0;
  color: #66758c;
  font-size: 13px;
}

.overview-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr);
  gap: 18px;
}

.toolbar-description {
  margin-top: 2px;
  color: #8390a3;
  font-size: 12px;
}

.toolbar-meta {
  color: #8390a3;
  font-size: 12px;
}

.primary-cell {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.primary-cell a {
  overflow: hidden;
  color: #1f5fa9;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.primary-cell span {
  color: #8a96a8;
  font-size: 11px;
}

.numeric-cell {
  font-variant-numeric: tabular-nums;
}

.overview-task-list {
  padding: 0 16px;
}

.overview-task-list :deep(.ant-list-item) {
  padding: 13px 0;
}

.overview-task-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: #28364b;
  font-size: 13px;
  font-weight: 600;
}

.overview-task-description {
  display: grid;
  gap: 4px;
}

.overview-task-description > span {
  overflow: hidden;
  color: #66758c;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.overview-task-description time {
  color: #9aa5b5;
  font-size: 11px;
}
</style>
