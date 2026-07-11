<template>
  <section class="metric-card" :class="`metric-card--${tone}`">
    <div class="metric-card__head">
      <span class="metric-card__label">{{ label }}</span>
      <span v-if="$slots.icon" class="metric-card__icon"><slot name="icon" /></span>
    </div>
    <div class="metric-card__value">{{ value }}</div>
    <div v-if="hint" class="metric-card__hint">{{ hint }}</div>
  </section>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  label: string;
  value: string | number;
  hint?: string;
  tone?: "default" | "positive" | "warning" | "danger";
}>(), {
  hint: "",
  tone: "default",
});
</script>
