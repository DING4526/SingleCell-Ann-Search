<template>
  <div class="not-found-view">
    <a-result status="404" title="页面未找到" sub-title="该地址不存在，或页面已经迁移。">
      <template #extra>
        <a-space>
          <a-button @click="$router.back()">返回上一页</a-button>
          <a-button type="primary" @click="$router.replace('/overview')">返回概览</a-button>
        </a-space>
      </template>
    </a-result>
  </div>
</template>

<style scoped>
.not-found-view {
  display: grid;
  min-height: calc(100vh - 108px);
  place-items: center;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  background: #fff;
}
</style>
