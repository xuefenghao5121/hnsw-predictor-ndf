import type { Snapshot } from "./types";

declare global {
  interface Window {
    __NDF_SNAPSHOT__?: Snapshot;
    __NDF_STANDALONE__?: boolean;
  }
}

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
  if (window.__NDF_SNAPSHOT__) {
    return window.__NDF_SNAPSHOT__;
  }
  const response = await fetch("/snapshot.json", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`snapshot HTTP ${response.status}`);
  }
  try {
    return (await response.json()) as Snapshot;
  } catch (err) {
    throw new Error(err instanceof Error ? err.message : "snapshot JSON parse failed");
  }
}

export async function dispatchAction(request: ActionRequest): Promise<ActionResponse> {
  if (window.__NDF_STANDALONE__) {
    const detail = [
      `action_id=${request.id}`,
      request.topic ? `topic=${request.topic}` : "",
      request.episode ? `episode=${request.episode}` : "",
      request.intent ? `intent=${request.intent}` : "",
      "在当前 Cloud Agent 对话执行这个 NDF hop。",
      "Button click is not a human gate.",
      "MUST NOT write .openclaw/state.json from Cursor.",
    ].filter(Boolean);
    return {
      id: request.id,
      dispatch: "composer",
      prompt: detail.join("\n"),
    };
  }
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
