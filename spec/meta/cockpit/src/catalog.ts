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
