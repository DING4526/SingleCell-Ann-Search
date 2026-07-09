import { createApp } from "vue";
import { createPinia } from "pinia";
import Antd, { theme } from "ant-design-vue";
import "ant-design-vue/dist/reset.css";
import App from "@/App.vue";
import { router } from "@/router";
import "@/styles/research-platform.css";

const app = createApp(App);
app.use(createPinia());
app.use(router);
app.use(Antd);
app.provide("themeConfig", {
  algorithm: theme.defaultAlgorithm,
  token: {
    colorPrimary: "#2563eb",
    colorInfo: "#0891b2",
    colorSuccess: "#059669",
    colorWarning: "#d97706",
    colorError: "#dc2626",
    borderRadius: 8,
    fontFamily: "Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  },
});
app.mount("#app");
