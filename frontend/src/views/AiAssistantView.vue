<template>
  <div>
    <PageHeader title="AI 研究助手" description="围绕当前工作区完成平台问答、知识检索，以及由你确认后执行的单细胞科学分析。">
      <template #actions>
        <a-button @click="$router.push('/ai-knowledge')">打开知识库</a-button>
      </template>
    </PageHeader>
    <a-alert
      class="assistant-notice"
      type="info"
      show-icon
      message="分析与平台操作始终由你确认"
      description="助手会先说明目标、参数和影响；删除、权限、所有权与模型配置不会交由 AI 执行。"
    />
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
