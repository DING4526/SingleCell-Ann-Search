<template>
  <div>
    <PageHeader title="AI 助手" description="在同一会话中完成平台问答、页面操作、知识检索和可确认的单细胞科学分析。">
      <template #actions>
        <a-button @click="$router.push('/ai-knowledge')">管理知识库</a-button>
      </template>
    </PageHeader>
    <a-alert class="assistant-notice" type="info" show-icon message="ANN 检索和写操作都会先展示计划并由你确认；删除、权限、所有权和模型配置不会交给 AI 执行。" />
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
