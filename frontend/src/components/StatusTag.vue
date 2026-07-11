<template>
  <a-tag class="status-tag" :color="statusColor(status)" :bordered="false" :title="statusText(status)">
    <span class="status-tag__dot" aria-hidden="true" />
    {{ statusText(status) }}
  </a-tag>
</template>

<script setup lang="ts">
import { statusColor, statusText } from "@/utils/format";

defineProps<{
  status: string;
}>();
</script>
