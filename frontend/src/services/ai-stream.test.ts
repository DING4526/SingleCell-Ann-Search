import { describe, expect, it } from "vitest";
import { analysisModeForTool, reduceAiStreamEvent, toolForAnalysisMode } from "./ai-stream";

describe("AI stream UI reducer", () => {
  it("merges deltas and clears provisional text on a validated replacement", () => {
    const initial = { enhancement: "", terminal: false, refresh: false, stageMessage: null };
    const first = reduceAiStreamEvent(initial, "answer.delta", { delta: "中文" });
    const second = reduceAiStreamEvent(first, "answer.delta", { delta: "解读" });
    expect(second.enhancement).toBe("中文解读");
    const replaced = reduceAiStreamEvent(second, "answer.replace", { content: "已校验回答" });
    expect(replaced.enhancement).toBe("");
    expect(replaced.refresh).toBe(true);
  });

  it("marks completion terminal and maps all supported analysis modes", () => {
    const completed = reduceAiStreamEvent(
      { enhancement: "临时", terminal: false, refresh: false, stageMessage: null },
      "run.completed",
      { status: "success" },
    );
    expect(completed.terminal).toBe(true);
    expect(analysisModeForTool("run_joint_search")).toBe("joint");
    expect(analysisModeForTool("run_fanout_search")).toBe("fanout");
    expect(toolForAnalysisMode("single")).toBe("run_single_cell_search");
  });

  it("refreshes action and navigation events without ending the run", () => {
    const initial = { enhancement: "", terminal: false, refresh: false, stageMessage: null };
    const proposed = reduceAiStreamEvent(initial, "action.proposed", { tool_call_id: 3 });
    expect(proposed.refresh).toBe(true);
    expect(proposed.terminal).toBe(false);
    const navigation = reduceAiStreamEvent(initial, "ui.navigate", { path: "/query-lab" });
    expect(navigation.refresh).toBe(true);
    expect(navigation.terminal).toBe(false);
  });
});
