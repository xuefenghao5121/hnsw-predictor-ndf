import type { Snapshot } from "./types";

export type ActionRequest = {
  id: string;
  intent?: string;
  topic?: string;
  episode?: string;
  timelineStep?: number;
};

export type ActionResponse = {
  id: string;
  dispatch: string;
  enabled?: boolean;
  reason?: string | null;
  prompt?: string;
  path?: string | null;
  humanPhrase?: string | null;
  snapshot?: Snapshot;
  error?: string;
};

export async function loadSnapshot(): Promise<Snapshot> {
  const response = await fetch("/snapshot.json", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`snapshot HTTP ${response.status}`);
  }
  return (await response.json()) as Snapshot;
}

export async function dispatchAction(request: ActionRequest): Promise<ActionResponse> {
  const response = await fetch("/api/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  const payload = (await response.json()) as ActionResponse;
  if (!response.ok && !payload.prompt && !payload.path) {
    throw new Error(payload.error || `action HTTP ${response.status}`);
  }
  return payload;
}
