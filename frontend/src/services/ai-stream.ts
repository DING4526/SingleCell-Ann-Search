export type AiStreamUiState = {
  enhancement: string;
  terminal: boolean;
  refresh: boolean;
  stageMessage: string | null;
};

export function reduceAiStreamEvent(
  state: AiStreamUiState,
  eventType: string,
  payload: Record<string, unknown>,
): AiStreamUiState {
  if (eventType === "answer.delta") {
    return { ...state, enhancement: state.enhancement + String(payload.delta || ""), refresh: false };
  }
  if (eventType === "run.stage") {
    return { ...state, stageMessage: String(payload.message || payload.label || ""), refresh: false };
  }
  if (["plan.ready", "answer.replace", "action.proposed", "action.status", "ui.navigate", "assistant.handoff"].includes(eventType)) {
    return { ...state, enhancement: "", refresh: true };
  }
  if (eventType === "answer.completed" || eventType === "run.completed") {
    return { ...state, enhancement: "", terminal: true, refresh: true };
  }
  return { ...state, refresh: false };
}

export function analysisModeForTool(tool?: string): "single" | "fanout" | "joint" {
  if (tool === "run_joint_search") return "joint";
  if (tool === "run_fanout_search") return "fanout";
  return "single";
}

export function toolForAnalysisMode(mode: "single" | "fanout" | "joint") {
  if (mode === "joint") return "run_joint_search";
  if (mode === "fanout") return "run_fanout_search";
  return "run_single_cell_search";
}
