<template>
  <section class="scientific-plot" :aria-busy="rendering">
    <div v-if="legendItems.length || roleItems.length" class="plot-toolbar">
      <div class="plot-toolbar__left">
        <a-segmented
          v-if="dimensionOptions.length > 1"
          v-model:value="activeDimension"
          size="small"
          :options="dimensionOptions"
          @change="resetLegend"
        />
        <span v-for="item in roleItems" :key="item.label" class="role-key">
          <i :style="{ background: item.color }" />{{ item.label }}
        </span>
        <span v-if="pointSummary && pointSummary.rendered < pointSummary.total" class="point-summary">
          显示 {{ formatCount(pointSummary.rendered) }} / {{ formatCount(pointSummary.total) }} 个细胞
        </span>
      </div>
      <a-popover placement="bottomRight" trigger="click" overlay-class-name="plot-legend-popover">
        <template #content>
          <div class="legend-panel">
            <div class="legend-panel__head">
              <div>
                <strong>{{ activeDimensionLabel }}</strong>
                <span>单击隐藏，双击独显</span>
              </div>
              <a-button type="link" size="small" @click="showAll">显示全部</a-button>
            </div>
            <div class="legend-list">
              <button
                v-for="item in legendItems"
                :key="item.key"
                type="button"
                class="legend-item"
                :class="{ 'is-muted': hiddenKeys.has(item.key) }"
                :aria-pressed="!hiddenKeys.has(item.key)"
                @click="toggleLegendItem(item.key)"
                @dblclick.prevent="isolateLegendItem(item.key)"
              >
                <i :style="{ background: item.color }" />
                <span :title="item.label">{{ item.label }}</span>
                <em>{{ formatCount(item.count) }}</em>
              </button>
            </div>
          </div>
        </template>
        <a-button size="small" class="legend-trigger">
          图例 <span>{{ visibleLegendCount }}/{{ legendItems.length }}</span>
        </a-button>
      </a-popover>
    </div>

    <div v-if="!payload" class="plot-empty">
      <a-empty description="暂无可视化结果" />
    </div>
    <div v-else-if="renderError" class="plot-error">
      <a-alert type="error" show-icon message="图表暂时无法显示" :description="renderError">
        <template #action><a-button size="small" @click="renderPlot(payload)">重新加载</a-button></template>
      </a-alert>
    </div>
    <div
      v-show="payload && !renderError"
      ref="plotRef"
      class="plot-box"
      :style="boxStyle"
      role="img"
      :aria-label="plotAriaLabel"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { PlotlyPayload } from "@/types";

type LegendItem = { key: string; label: string; color: string; count: number };
type LegendDimension = { label: string; customdata_index: number; items: LegendItem[] };
type LegendContract = {
  target_trace_index: number;
  default_dimension: string;
  dimensions: Record<string, LegendDimension>;
  role_items?: Array<{ label: string; color: string }>;
};

const props = withDefaults(defineProps<{
  payload: PlotlyPayload | null;
  interactive?: boolean;
  height?: number;
  modeBar?: boolean;
  ariaLabel?: string;
}>(), {
  interactive: true,
  height: undefined,
  modeBar: undefined,
  ariaLabel: "单细胞嵌入空间图",
});

const emit = defineEmits<{
  pointClick: [payload: { customdata: unknown; point: Record<string, unknown>; action?: Record<string, unknown> }];
}>();

const plotRef = ref<HTMLDivElement | null>(null);
const rendering = ref(false);
const renderError = ref("");
const activeDimension = ref("");
const hiddenKeys = ref<Set<string>>(new Set());
let plotlyPromise: Promise<any> | null = null;

const boxStyle = computed(() => ({
  minHeight: `${props.height || 480}px`,
  height: `${props.height || 480}px`,
}));
const metadata = computed(() => (props.payload?.metadata || {}) as Record<string, any>);
const legend = computed<LegendContract | null>(() => metadata.value.legend || null);
const dimensionOptions = computed(() => Object.entries(legend.value?.dimensions || {}).map(([value, item]) => ({
  value,
  label: item.label,
})));
const currentDimension = computed(() => legend.value?.dimensions?.[activeDimension.value] || null);
const activeDimensionLabel = computed(() => currentDimension.value?.label || "图例");
const legendItems = computed(() => currentDimension.value?.items || []);
const roleItems = computed(() => legend.value?.role_items || []);
const pointSummary = computed<{ rendered: number; total: number } | null>(() => metadata.value.point_summary || null);
const visibleLegendCount = computed(() => legendItems.value.filter((item) => !hiddenKeys.value.has(item.key)).length);
const plotAriaLabel = computed(() => `${props.ariaLabel}。${activeDimensionLabel.value}图例共 ${legendItems.value.length} 项。`);

async function getPlotly() {
  if (!plotlyPromise) {
    // Keep Plotly lazy. The local runtime registers ScatterGL only.
    plotlyPromise = import("@/services/plotly-runtime").then((module) => module.default || module);
  }
  return plotlyPromise;
}

function formatCount(value: number) {
  return Number(value || 0).toLocaleString("zh-CN");
}

function clonePlotValue<T>(value: T): T {
  // API plot payloads are JSON-safe. JSON cloning also unwraps Vue's nested
  // reactive proxies, which `structuredClone` rejects with DataCloneError.
  return JSON.parse(JSON.stringify(value)) as T;
}

function initializeLegend(payload: PlotlyPayload | null) {
  const contract = (payload?.metadata as Record<string, any> | undefined)?.legend as LegendContract | undefined;
  activeDimension.value = contract?.default_dimension || Object.keys(contract?.dimensions || {})[0] || "";
  hiddenKeys.value = new Set();
}

async function renderPlot(payload: PlotlyPayload | null) {
  renderError.value = "";
  await nextTick();
  if (!plotRef.value) return;
  const Plotly = await getPlotly();
  if (!payload) {
    Plotly.purge(plotRef.value);
    return;
  }

  rendering.value = true;
  try {
    const interactive = props.interactive;
    const sourceLayout = payload.layout || {};
    const sourceMargin = (sourceLayout.margin as Record<string, number> | undefined) || {};
    const layout = {
      ...sourceLayout,
      paper_bgcolor: "#ffffff",
      plot_bgcolor: "#ffffff",
      showlegend: false,
      font: { color: "#172033", size: 12 },
      hovermode: "closest",
      dragmode: interactive ? "pan" : false,
      height: props.height || sourceLayout.height || 480,
      margin: {
        l: Math.max(sourceMargin.l || 0, 52),
        r: 24,
        t: Math.max(Math.min(sourceMargin.t || 0, 54), 42),
        b: Math.max(sourceMargin.b || 0, 48),
      },
      xaxis: {
        ...(sourceLayout.xaxis as Record<string, unknown> | undefined),
        gridcolor: "#edf2f7",
        zeroline: false,
        linecolor: "#d8e1ec",
        automargin: true,
      },
      yaxis: {
        ...(sourceLayout.yaxis as Record<string, unknown> | undefined),
        gridcolor: "#edf2f7",
        zeroline: false,
        linecolor: "#d8e1ec",
        automargin: true,
      },
    };
    // Plotly mutates trace/layout objects internally. Clone the JSON-safe API
    // payload so those mutations cannot reset Vue legend state or stale-mode
    // guards through a deep reactive watcher.
    await Plotly.react(plotRef.value, clonePlotValue(payload.data) as never[], clonePlotValue(layout), {
      responsive: true,
      displaylogo: false,
      displayModeBar: props.modeBar ?? interactive,
      scrollZoom: interactive,
      staticPlot: !interactive,
      doubleClick: interactive ? "reset+autosize" : false,
      modeBarButtonsToRemove: [
        "select2d", "lasso2d", "zoomIn2d", "zoomOut2d", "autoScale2d",
        "hoverClosestCartesian", "hoverCompareCartesian", "toggleSpikelines",
      ],
      toImageButtonOptions: {
        format: "png",
        filename: "single-cell-ann-plot",
        scale: 2,
      },
    });

    const graph = plotRef.value as HTMLDivElement & {
      on?: (name: string, callback: (event: any) => void) => void;
      removeAllListeners?: (name: string) => void;
    };
    graph.removeAllListeners?.("plotly_click");
    graph.on?.("plotly_click", (event) => {
      const point = event?.points?.[0];
      if (!point) return;
      emit("pointClick", {
        customdata: point.customdata,
        point,
        action: metadata.value.point_action,
      });
    });
  } catch (error) {
    renderError.value = (error as Error).message || "图表渲染失败，请重新加载。";
  } finally {
    rendering.value = false;
  }
}

async function applyLegendFilter() {
  if (!plotRef.value || !props.payload || !legend.value || !currentDimension.value) return;
  const traceIndex = legend.value.target_trace_index ?? 0;
  const trace = (props.payload.data as Array<Record<string, any>>)[traceIndex];
  const customdata = Array.isArray(trace?.customdata) ? trace.customdata : [];
  if (!customdata.length) return;
  const itemColors = new Map(legendItems.value.map((item) => [String(item.key), item.color]));
  const categoryIndex = currentDimension.value.customdata_index;
  const baseOpacity = typeof trace?.marker?.opacity === "number" ? trace.marker.opacity : 0.72;
  const colors = customdata.map((row: unknown[]) => itemColors.get(String(row?.[categoryIndex] ?? "未知")) || "#94a3b8");
  const opacities = customdata.map((row: unknown[]) => hiddenKeys.value.has(String(row?.[categoryIndex] ?? "未知")) ? 0.035 : baseOpacity);
  const Plotly = await getPlotly();
  await Plotly.restyle(plotRef.value, {
    "marker.color": [colors],
    "marker.opacity": [opacities],
  }, [traceIndex]);
}

function toggleLegendItem(key: string) {
  const next = new Set(hiddenKeys.value);
  if (next.has(key)) next.delete(key); else next.add(key);
  hiddenKeys.value = next;
  applyLegendFilter();
}

function isolateLegendItem(key: string) {
  hiddenKeys.value = new Set(legendItems.value.filter((item) => item.key !== key).map((item) => item.key));
  applyLegendFilter();
}

function showAll() {
  hiddenKeys.value = new Set();
  applyLegendFilter();
}

function resetLegend() {
  hiddenKeys.value = new Set();
  applyLegendFilter();
}

watch(() => props.payload, async (payload) => {
  initializeLegend(payload);
  await renderPlot(payload);
});

watch(() => [props.interactive, props.height, props.modeBar], () => renderPlot(props.payload));

onMounted(() => {
  initializeLegend(props.payload);
  renderPlot(props.payload);
});

onBeforeUnmount(async () => {
  if (plotRef.value) {
    const Plotly = await getPlotly();
    Plotly.purge(plotRef.value);
  }
});
</script>

<style scoped>
.scientific-plot {
  min-width: 0;
  background: #fff;
}

.plot-toolbar {
  min-height: 40px;
  padding: 6px 10px;
  border-bottom: 1px solid #eef2f7;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.plot-toolbar__left {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.role-key {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #64748b;
  font-size: 12px;
}

.point-summary {
  color: #7b8798;
  font-size: 11px;
}

.role-key i,
.legend-item i {
  display: inline-block;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex: 0 0 auto;
}

.legend-trigger span {
  color: #64748b;
  margin-left: 4px;
}

.plot-empty {
  min-height: 320px;
  display: grid;
  place-items: center;
}

.plot-error {
  min-height: 180px;
  padding: 20px;
}

.plot-box {
  width: 100%;
  min-width: 0;
}

.legend-panel {
  width: 300px;
}

.legend-panel__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #eef2f7;
}

.legend-panel__head strong,
.legend-panel__head span {
  display: block;
}

.legend-panel__head span {
  margin-top: 2px;
  color: #94a3b8;
  font-size: 11px;
}

.legend-list {
  max-height: 320px;
  overflow: auto;
  padding: 6px 2px 2px;
}

.legend-item {
  width: 100%;
  border: 0;
  background: transparent;
  padding: 7px 6px;
  border-radius: 6px;
  display: grid;
  grid-template-columns: 12px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  color: #334155;
  text-align: left;
  cursor: pointer;
}

.legend-item:hover {
  background: #f6f8fb;
}

.legend-item span {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.legend-item em {
  color: #94a3b8;
  font-size: 11px;
  font-style: normal;
  font-variant-numeric: tabular-nums;
}

.legend-item.is-muted {
  color: #94a3b8;
  opacity: 0.56;
}
</style>
