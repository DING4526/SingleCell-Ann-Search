import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth";

const routes = [
  { path: "/", redirect: "/overview" },
  { path: "/login", name: "login", component: () => import("@/views/LoginView.vue"), meta: { public: true } },
  { path: "/overview", name: "overview", component: () => import("@/views/OverviewView.vue") },
  { path: "/datasets", name: "datasets", component: () => import("@/views/DatasetsView.vue") },
  { path: "/datasets/:id", name: "dataset-detail", component: () => import("@/views/DatasetDetailView.vue") },
  { path: "/index-lab", name: "index-lab", component: () => import("@/views/IndexLabView.vue") },
  { path: "/joint-indexes", name: "joint-indexes", component: () => import("@/views/JointIndexesView.vue") },
  { path: "/query-lab", name: "query-lab", component: () => import("@/views/QueryLabView.vue") },
  { path: "/evaluation", redirect: "/index-lab" },
  { path: "/access", name: "access", component: () => import("@/views/AccessView.vue") },
  { path: "/ai-analysis", name: "ai-analysis", component: () => import("@/views/AiAnalysisView.vue") },
  { path: "/:pathMatch(.*)*", redirect: "/overview" },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
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
