import { actionsById, type RegistryAction } from "./catalog";

/** Five-stage workbench axis (prototype v3.1). */
export type PhaseId = "explore" | "bind" | "gate" | "execute" | "promote";

export type PhaseState = "done" | "active" | "blocked" | "pending";

export const PHASES: Array<{
  id: PhaseId;
  label: string;
  short: string;
  desc: string;
}> = [
  { id: "explore", label: "探索", short: "explore", desc: "提案 → DESIGN" },
  { id: "bind", label: "装订", short: "bind", desc: "六面 + 基线" },
  { id: "gate", label: "门禁", short: "gate", desc: "三闸人口令" },
  { id: "execute", label: "执行", short: "execute", desc: "POC / 测量" },
  { id: "promote", label: "晋升", short: "promote", desc: "收口 / 金标" },
];

/**
 * Map existing registry actions into phases.
 * Prefer tab/module/provider; do NOT invent new action ids.
 * human-phrase is NOT an action — gate Human zone projects gate-pipeline humanPhrase.
 */
export const ACTION_PHASE: Record<string, PhaseId | "_all"> = {
  "design-prepare": "explore",
  "poc-prepare-baseline": "bind",
  "binder-pipeline": "bind",
  "binder-amend": "bind",
  "gate-pipeline": "gate",
  "delegate-poc": "execute",
  "poc-measurement": "execute",
  "poc-isolation-repair": "execute",
  "diagnose-topic": "execute",
  "open-delta": "execute",
  "prepare-acp-lease": "execute",
  "generate-next-step": "execute",
  "next-close-hop": "promote",
  "align-golden": "promote",
  "refresh-snapshot": "_all",
  "refresh-topic": "_all",
  "command-replay-run": "_all",
  "command-replay-compare": "_all",
};

/** Primary hero action for the execute phase. */
export const HERO_ACTION_ID = "delegate-poc";

/** Workbench left-rail allowlist (registry ids unchanged). */
export const SIDEBAR_ACTIONS: Record<PhaseId, string[]> = {
  explore: [],
  bind: ["binder-pipeline", "binder-amend", "poc-prepare-baseline"],
  gate: ["gate-pipeline"],
  execute: ["delegate-poc"],
  promote: ["align-golden", "next-close-hop"],
};

export const GLOBAL_SIDEBAR_ACTIONS = ["refresh-snapshot", "refresh-topic", "command-replay-run", "command-replay-compare"];

export function sidebarActionsForPhase(phase: PhaseId): string[] {
  return SIDEBAR_ACTIONS[phase].filter((id) => actionsById[id]?.commanderSurface !== false);
}

export function phaseOf(actionId: string): PhaseId | "_all" | null {
  if (ACTION_PHASE[actionId]) return ACTION_PHASE[actionId];
  const action = actionsById[actionId];
  if (!action) return null;
  return inferPhaseFromRegistry(action);
}

function inferPhaseFromRegistry(action: RegistryAction): PhaseId | "_all" | null {
  if (action.tab === "replay") return "_all";
  if (action.module === "space-design" || action.id.includes("design")) return "explore";
  if (action.module === "binder" || action.id.includes("binder") || action.id.includes("baseline")) {
    return "bind";
  }
  if (action.module === "gate" || action.id.includes("gate")) return "gate";
  if (action.module === "decision" || action.id.includes("delegate") || action.id.includes("poc-")) {
    return "execute";
  }
  if (action.id.includes("close") || action.id.includes("golden") || action.id.includes("promote")) {
    return "promote";
  }
  return null;
}

export function actionsForPhase(phase: PhaseId): string[] {
  return Object.entries(ACTION_PHASE)
    .filter(([, p]) => p === phase || p === "_all")
    .map(([id]) => id)
    .filter((id) => actionsById[id]?.commanderSurface !== false);
}

export type ProviderKind = "openclaw" | "claude-code" | "human" | "tool" | "none";

export function providerKind(action: RegistryAction): ProviderKind {
  const p = (action.provider || "").toLowerCase();
  if (p.includes("openclaw")) return "openclaw";
  if (p.includes("claude") || p.includes("acp")) return "claude-code";
  if (action.humanPhrase && action.dispatch === "composer" && action.id === "gate-pipeline") {
    return "human";
  }
  if (!p || p === "none") return "tool";
  return "tool";
}

export function providerTagClass(kind: ProviderKind): string {
  switch (kind) {
    case "openclaw":
      return "tag-oc";
    case "claude-code":
      return "tag-cc";
    case "human":
      return "tag-hu";
    default:
      return "tag-tool";
  }
}

export function providerLabel(kind: ProviderKind): string {
  switch (kind) {
    case "openclaw":
      return "OpenClaw";
    case "claude-code":
      return "Claude Code";
    case "human":
      return "Human";
    default:
      return "Tool";
  }
}
