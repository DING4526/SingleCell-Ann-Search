<template>
  <div ref="plotRef" class="plot-box" />
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import Plotly from "plotly.js-dist-min";
import type { PlotlyPayload } from "@/types";

const props = defineProps<{
  payload: PlotlyPayload | null;
}>();

const plotRef = ref<HTMLDivElement | null>(null);

async function renderPlot(payload: PlotlyPayload | null) {
  await nextTick();
  if (!plotRef.value || !payload) return;
  const sourceLayout = payload.layout || {};
  const sourceMargin = (sourceLayout.margin as Record<string, number> | undefined) || {};
  const sourceLegend = (sourceLayout.legend as Record<string, unknown> | undefined) || {};
  const layout = {
    ...sourceLayout,
    paper_bgcolor: "#ffffff",
    plot_bgcolor: "#ffffff",
    font: { color: "#172033", size: 12 },
    hovermode: "closest",
    dragmode: "pan",
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
    displayModeBar: true,
    scrollZoom: true,
    doubleClick: "reset+autosize",
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

onBeforeUnmount(() => {
  if (plotRef.value) Plotly.purge(plotRef.value);
});
</script>
