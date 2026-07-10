export type Capability = {
  key: string;
  title: string;
  status: "ready" | "planned";
  description: string;
  route: string;
};

export const capabilities: Capability[] = [
  { key: "hnsw", title: "单数据集索引", status: "ready", description: "稳定构建并检索单数据集 ANN 索引。", route: "/index-lab" },
  { key: "fanout", title: "跨数据集检索", status: "ready", description: "检索并合并兼容数据集索引结果。", route: "/query-lab" },
  { key: "merged-index", title: "联合索引", status: "ready", description: "基于 Harmony 对齐的多数据集物理索引。", route: "/index-lab" },
  { key: "multi-algorithm", title: "多算法评估", status: "ready", description: "对比 HNSW、RP-HNSW 与 FAISS IVF/PQ。", route: "/index-lab" },
  { key: "access", title: "访问控制", status: "planned", description: "用户、共享与数据集可见性管理。", route: "/access" },
  { key: "ai", title: "AI 分析", status: "planned", description: "自然语言查询和结果解释。", route: "/ai-analysis" },
];
