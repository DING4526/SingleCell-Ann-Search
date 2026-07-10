<template>
  <div ref="plotRef" class="plot-box" :style="boxStyle" />
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import Plotly from "plotly.js-dist-min";
import type { PlotlyPayload } from "@/types";

const props = withDefaults(defineProps<{
  payload: PlotlyPayload | null;
  interactive?: boolean;
  height?: number;
  modeBar?: boolean;
}>(), {
  interactive: true,
  height: undefined,
  modeBar: undefined,
});

const plotRef = ref<HTMLDivElement | null>(null);
const boxStyle = computed(() => (props.height ? { minHeight: `${props.height}px`, height: `${props.height}px` } : undefined));

async function renderPlot(payload: PlotlyPayload | null) {
  await nextTick();
  if (!plotRef.value || !payload) return;
  const interactive = props.interactive;
  const sourceLayout = payload.layout || {};
  const sourceMargin = (sourceLayout.margin as Record<string, number> | undefined) || {};
  const sourceLegend = (sourceLayout.legend as Record<string, unknown> | undefined) || {};
  const layout = {
    ...sourceLayout,
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    font: { color: "#172033", size: 12 },
    hovermode: "closest",
    dragmode: interactive ? "pan" : false,
    height: props.height || sourceLayout.height,
    margin: {
      l: Math.max(sourceMargin.l || 0, 52),
      r: Math.max(sourceMargin.r || 0, 148),
      t: Math.max(sourceMargin.t || 0, 48),
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
    legend: {
      ...sourceLegend,
      orientation: "v",
      x: 1.02,
      y: 1,
      xanchor: "left",
      yanchor: "top",
      bgcolor: "rgba(255,255,255,0.94)",
      bordercolor: "#e5eaf2",
      borderwidth: 1,
      font: { color: "#334155", size: 11 },
      title: { text: "图例" },
    },
  };
  await Plotly.react(plotRef.value, payload.data as never[], layout, {
    responsive: true,
    displaylogo: false,
    displayModeBar: props.modeBar ?? interactive,
    scrollZoom: interactive,
    staticPlot: !interactive,
    doubleClick: interactive ? "reset+autosize" : false,
    modeBarButtonsToRemove: ["select2d", "lasso2d"],
    toImageButtonOptions: {
      format: "png",
      filename: "single-cell-ann-plot",
      scale: 2,
    },
  });
}

watch(() => props.payload, renderPlot, { deep: true });

onMounted(() => {
  renderPlot(props.payload);
});

watch(() => [props.interactive, props.height, props.modeBar], () => renderPlot(props.payload));

onBeforeUnmount(() => {
  if (plotRef.value) Plotly.purge(plotRef.value);
});
</script>
