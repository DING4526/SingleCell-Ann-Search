// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { renderAssistantMarkdown, stripAssistantInternalMarkers } from "./assistant-markdown";

describe("assistant markdown", () => {
  it("renders GFM structure for assistant answers", () => {
    const html = renderAssistantMarkdown("## 结论\n\n- **索引**：HNSW\n- `Top-K=10`\n\n| 指标 | 数值 |\n| --- | --- |\n| Recall | 99% |");
    expect(html).toContain("<h2>结论</h2>");
    expect(html).toContain("<ul>");
    expect(html).toContain("<strong>索引</strong>");
    expect(html).toContain("<code>Top-K=10</code>");
    expect(html).toContain("<table>");
  });

  it("removes internal markers and unsafe markup", () => {
    const html = renderAssistantMarkdown("结果 [E:distance.min] [K:doc:1]\n\n<script>alert(1)</script><a href=\"javascript:alert(1)\" onclick=\"alert(2)\">危险链接</a>");
    expect(html).not.toContain("[E:");
    expect(html).not.toContain("[K:");
    expect(html).not.toContain("script");
    expect(html).not.toContain("javascript:");
    expect(html).not.toContain("onclick");
  });

  it("normalizes excessive blank lines", () => {
    expect(stripAssistantInternalMarkers("第一段\n\n\n\n第二段")).toBe("第一段\n\n第二段");
  });
});
