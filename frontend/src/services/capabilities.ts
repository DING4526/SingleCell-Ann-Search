export type Capability = {
  key: string;
  title: string;
  status: "ready" | "planned";
  description: string;
  route: string;
};

export const capabilities: Capability[] = [
  { key: "hnsw", title: "HNSW 索引", status: "ready", description: "当前稳定索引构建和查询能力。", route: "/index-lab" },
  { key: "fanout", title: "跨数据集检索", status: "ready", description: "跨数据集 fan-out 合并检索。", route: "/query-lab" },
  { key: "merged-index", title: "合并索引", status: "planned", description: "多数据集物理联合索引与全局 cell id。", route: "/index-lab" },
  { key: "multi-algorithm", title: "多算法实验", status: "planned", description: "FAISS IVF/PQ/HNSW 参数实验。", route: "/index-lab" },
  { key: "access", title: "权限管理", status: "planned", description: "用户、共享和数据集可见性管理。", route: "/access" },
  { key: "ai", title: "AI 分析", status: "planned", description: "自然语言查询和检索结果解释。", route: "/ai-analysis" },
];
