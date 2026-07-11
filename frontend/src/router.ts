import { createRouter, createWebHistory, type RouteLocationGeneric, type RouteRecordRaw } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const routes: RouteRecordRaw[] = [
  { path: "/", redirect: "/overview" },
  { path: "/login", name: "login", component: () => import("@/views/LoginView.vue"), meta: { public: true, title: "登录" } },
  { path: "/overview", name: "overview", component: () => import("@/views/OverviewView.vue"), meta: { title: "概览" } },
  { path: "/datasets", name: "datasets", component: () => import("@/views/DatasetsView.vue"), meta: { title: "数据资源" } },
  { path: "/datasets/:id", name: "dataset-detail", component: () => import("@/views/DatasetDetailView.vue"), meta: { title: "数据集详情" } },
  { path: "/index-lab", name: "index-lab", component: () => import("@/views/IndexLabView.vue"), meta: { title: "索引实验室" } },
  { path: "/joint-indexes", name: "joint-indexes", component: () => import("@/views/JointIndexesView.vue"), meta: { title: "联合索引" } },
  { path: "/query-lab", name: "query-lab", component: () => import("@/views/QueryLabView.vue"), meta: { title: "检索实验室" } },
  { path: "/evaluation", redirect: "/index-lab" },
  { path: "/access", name: "access", component: () => import("@/views/AccessView.vue"), meta: { title: "权限管理" } },
  { path: "/ai-analysis", redirect: (to: RouteLocationGeneric) => ({ path: "/ai-assistant", query: to.query }) },
  { path: "/ai-knowledge", name: "ai-knowledge", component: () => import("@/views/AiKnowledgeView.vue"), meta: { title: "AI 知识库" } },
  { path: "/ai-assistant", name: "ai-assistant", component: () => import("@/views/AiAssistantView.vue"), meta: { title: "AI 助手" } },
  { path: "/:pathMatch(.*)*", name: "not-found", component: () => import("@/views/NotFoundView.vue"), meta: { title: "页面未找到" } },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0, left: 0 }),
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();
  await auth.init();
  if (!to.meta.public && !auth.authenticated) {
    return { name: "login", query: { next: to.fullPath } };
  }
  if (to.meta.public && auth.authenticated) {
    return { name: "overview" };
  }
  return true;
});

router.afterEach((to) => {
  const pageTitle = typeof to.meta.title === "string" ? to.meta.title : "研究工作台";
  document.title = `${pageTitle} · 单细胞 ANN 研究平台`;
});
