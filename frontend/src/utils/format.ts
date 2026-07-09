export function formatDate(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function statusText(status: string) {
  return {
    uploaded: "已上传",
    processed: "已处理",
    indexed: "已建索引",
    error: "错误",
    ready: "就绪",
    building: "构建中",
    pending: "等待",
    running: "运行中",
    success: "完成",
  }[status] || status;
}

export function statusColor(status: string) {
  if (["indexed", "ready", "success"].includes(status)) return "success";
  if (["processed", "running", "building"].includes(status)) return "processing";
  if (["uploaded", "pending"].includes(status)) return "default";
  if (status === "error") return "error";
  return "default";
}

export function numberOrDash(value?: number | null) {
  return value === undefined || value === null ? "-" : value.toLocaleString();
}
