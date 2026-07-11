import { createApp } from "vue";
import { createPinia } from "pinia";
import theme from "ant-design-vue/es/theme";
import zhCN from "ant-design-vue/es/locale/zh_CN";
import "ant-design-vue/dist/reset.css";
import App from "@/App.vue";
import { router } from "@/router";
import "@/styles/research-platform.css";

const app = createApp(App);
app.use(createPinia());
app.use(router);
app.provide("localeConfig", zhCN);
app.provide("themeConfig", {
  algorithm: theme.defaultAlgorithm,
  token: {
    colorPrimary: "#1f5fa9",
    colorInfo: "#1677a7",
    colorSuccess: "#16865f",
    colorWarning: "#b86908",
    colorError: "#c43d3d",
    colorText: "#17243a",
    colorTextSecondary: "#66758c",
    colorBorder: "#dfe5ed",
    colorBorderSecondary: "#edf0f4",
    colorBgLayout: "#f4f6f9",
    borderRadius: 8,
    borderRadiusLG: 10,
    controlHeight: 36,
    fontSize: 14,
    fontFamily: "Inter, 'PingFang SC', 'Microsoft YaHei', ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  },
  components: {
    Button: { fontWeight: 500 },
    Card: { paddingLG: 18 },
    Drawer: { paddingLG: 20 },
    Form: { itemMarginBottom: 18, labelColor: "#334155" },
    Layout: { bodyBg: "#f4f6f9", headerBg: "#ffffff", siderBg: "#ffffff" },
    Menu: { itemHeight: 40, itemBorderRadius: 7, itemMarginInline: 8 },
    Table: { cellPaddingBlock: 11, cellPaddingInline: 12, cellPaddingBlockSM: 8, cellPaddingInlineSM: 12, headerBg: "#f7f9fb", headerColor: "#36445a" },
    Tabs: { horizontalItemPadding: "10px 2px" },
  },
});
app.mount("#app");
