<template>
  <div>
    <PageHeader title="全局 AI 助手" description="结合当前页面和平台实时状态，用自然语言导航、预填并安全调用平台功能。">
      <template #actions>
        <a-button @click="$router.push('/ai-analysis')">进入 AI Analysis</a-button>
        <a-button @click="$router.push('/ai-knowledge')">管理知识库</a-button>
      </template>
    </PageHeader>
    <a-alert class="assistant-notice" type="info" show-icon message="写操作始终先生成草案并由你确认；删除、权限、所有权和模型配置不会交给 AI 执行。" />
    <GlobalAiAssistant embedded />
  </div>
</template>

<script setup lang="ts">
import PageHeader from "@/components/PageHeader.vue";
import GlobalAiAssistant from "@/components/ai/GlobalAiAssistant.vue";
</script>

<style scoped>
.assistant-notice { margin-bottom: 14px; }
</style>
