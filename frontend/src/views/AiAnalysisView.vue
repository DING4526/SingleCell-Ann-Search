<template>
  <PageHeader title="AI 分析" description="自然语言查询、RAG 和细胞分析摘要将在这里接入，不干扰现有检索主链路。" />

  <div class="two-column">
    <div class="surface surface-pad">
      <div class="panel-title">规划工作流</div>
      <a-timeline>
        <a-timeline-item>自然语言解析为结构化检索参数</a-timeline-item>
        <a-timeline-item>调用检索实验室的检索 API</a-timeline-item>
        <a-timeline-item>结合 Top-K、元信息分布和评估指标生成解释</a-timeline-item>
      </a-timeline>
    </div>
    <div class="surface surface-pad">
      <div class="panel-title">原型提示区</div>
      <a-textarea placeholder="例如：在 Hepatocyte 中找到与 123 号细胞最相似的 20 个细胞，并解释疾病和年龄组分布。" :rows="8" disabled />
      <a-button style="margin-top:12px" disabled>AI 接入规划中</a-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import PageHeader from "@/components/PageHeader.vue";
</script>
