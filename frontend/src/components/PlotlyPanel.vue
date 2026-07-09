<template>
  <div ref="plotRef" class="plot-box" />
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from "vue";
import Plotly from "plotly.js-dist-min";
import type { PlotlyPayload } from "@/types";

const props = defineProps<{
  payload: PlotlyPayload | null;
}>();

const plotRef = ref<HTMLDivElement | null>(null);

watch(
  () => props.payload,
  async (payload) => {
    if (!plotRef.value || !payload) return;
    const layout = {
      ...payload.layout,
      paper_bgcolor: "#ffffff",
      plot_bgcolor: "#ffffff",
      font: { color: "#172033", size: 12 },
      margin: { l: 48, r: 24, t: 48, b: 48, ...(payload.layout?.margin as Record<string, unknown> | undefined) },
    };
    await Plotly.react(plotRef.value, payload.data as never[], layout, { responsive: true, displaylogo: false });
  },
  { immediate: true, deep: true },
);

onBeforeUnmount(() => {
  if (plotRef.value) Plotly.purge(plotRef.value);
});
</script>
