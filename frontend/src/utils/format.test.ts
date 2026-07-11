import { describe, expect, it } from "vitest";
import { algorithmText, formatCellIndex, formatDistance, formatMilliseconds, metricText, statusText } from "@/utils/format";

describe("发布级显示格式", () => {
  it("把内部状态和算法键转换为用户可读文本", () => {
    expect(statusText("active")).toBe("可用于检索");
    expect(statusText("candidate")).toBe("待选优");
    expect(algorithmText("hnswlib_hnsw")).toBe("HNSW");
    expect(metricText("cosine")).toBe("余弦距离");
  });

  it("统一格式化细胞编号、距离和耗时", () => {
    expect(formatCellIndex(12345)).toBe("12,345");
    expect(formatDistance(10.696728)).toBe("10.6967");
    expect(formatMilliseconds(112.4582)).toBe("112.5 ms");
  });
});
