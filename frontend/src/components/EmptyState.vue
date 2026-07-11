<template>
  <div class="content-state content-state--empty">
    <a-empty :image="simpleImage" :description="description">
      <slot name="action" />
    </a-empty>
  </div>
</template>

<script setup lang="ts">
import Empty from "ant-design-vue/es/empty";

withDefaults(defineProps<{ description?: string }>(), {
  description: "暂无可展示的数据",
});

const simpleImage = Empty.PRESENTED_IMAGE_SIMPLE;
</script>
