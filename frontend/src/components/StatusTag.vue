<template>
  <a-tag :color="statusColor(status)">{{ statusText(status) }}</a-tag>
</template>

<script setup lang="ts">
import { statusColor, statusText } from "@/utils/format";

defineProps<{
  status: string;
}>();
</script>
