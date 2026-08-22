import registryJson from "../action-registry.json";

export type RegistryAction = {
  id: string;
  label: string;
  tab: string;
  module: string;
  clauseRefs: string[];
  dispatch: string;
  humanPhrase: string | null;
  requiresIntent: boolean;
  failClosed: "disable" | "hide";
  /** Optional ActionSpec fields used for display / routing (backward compatible). */
  provider?: string | null;
  skill?: string | null;
  packTask?: string | null;
  packKind?: string | null;
  operation?: string | null;
  commanderSurface?: boolean;
  /** Optional display phase override; prefer frontend ACTION_PHASE map. */
  phase?: string | null;
  why?: string | null;
};

type RegistryFile = {
  schema: string;
  actions: RegistryAction[];
  forbidden: Array<{ id: string; labels: string[] }>;
};

export const registry = registryJson as RegistryFile;
export const actionsById: Record<string, RegistryAction> = Object.fromEntries(
  registry.actions.map((item) => [item.id, item]),
);

export function requireAction(id: string): RegistryAction {
  const action = actionsById[id];
  if (!action) {
    throw new Error(`unregistered NDF action: ${id}`);
  }
  return action;
}

/** Closed-set check: every visible commander control must be registered or a known projection hook. */
export const PROJECTION_HOOKS = new Set([
  "collapse-section",
  "decision-prefill",
  "copy-prompt",
  "d3-zoom-filter",
  "mod-overview",
  "mod-workbench",
  "plane-product",
  "plane-control",
  "plane-runtime",
  "plane-replay",
  "phase-explore",
  "phase-bind",
  "phase-gate",
  "phase-execute",
  "phase-promote",
  "btn-acts",
  "btn-proj",
  "jump-human-phrase",
  "enter-workbench",
]);

export function isRegisteredOrHook(id: string): boolean {
  return Boolean(actionsById[id]) || PROJECTION_HOOKS.has(id);
}
