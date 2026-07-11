<template>
  <div class="content-state content-state--error" role="alert">
    <div class="content-state__icon"><WarningOutlined /></div>
    <div>
      <strong>{{ title }}</strong>
      <p>{{ description }}</p>
    </div>
    <a-button v-if="retryable" @click="$emit('retry')">重新加载</a-button>
  </div>
</template>

<script setup lang="ts">
import { WarningOutlined } from "@ant-design/icons-vue";

withDefaults(defineProps<{
  title?: string;
  description?: string;
  retryable?: boolean;
}>(), {
  title: "内容加载失败",
  description: "暂时无法获取数据，请稍后重试。",
  retryable: true,
});

defineEmits<{ retry: [] }>();
</script>
