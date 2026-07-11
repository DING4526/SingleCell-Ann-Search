<template>
  <a-config-provider :theme="themeConfig" :locale="localeConfig">
    <router-view v-if="isPublicRoute" />
    <AppLayout v-else />
  </a-config-provider>
</template>

<script setup lang="ts">
import { computed, inject } from "vue";
import { useRoute } from "vue-router";
import AppLayout from "@/components/AppLayout.vue";

const route = useRoute();
const isPublicRoute = computed(() => !!route.meta.public);
const themeConfig = inject("themeConfig");
const localeConfig = inject("localeConfig");
</script>
