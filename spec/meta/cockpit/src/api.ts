import type { Snapshot } from "./types";

declare global {
  interface Window {
    __NDF_SNAPSHOT__?: Snapshot;
    __NDF_STANDALONE__?: boolean;
    __NDF_ACTION_RESPONSES__?: Record<string, ActionResponse>;
  }
}

export type ActionRequest = {
  id: string;
  intent?: string;
  topic?: string;
  episode?: string;
  timelineStep?: number;
  remote?: string;
  remoteUrl?: string;
  branch?: string;
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

function gitInputs(request: ActionRequest): {
  remote: string;
  remoteUrl: string;
  branch: string;
  upstream: string;
} {
  const snapshot = window.__NDF_SNAPSHOT__;
  const remote =
    request.remote?.trim() ||
    snapshot?.git?.remote ||
    snapshot?.repoRemote ||
    "origin";
  const remoteUrl =
    request.remoteUrl?.trim() ||
    snapshot?.git?.remoteUrl ||
    snapshot?.repoRemoteUrl ||
    "<unresolved-remote-url>";
  const branch =
    request.branch?.trim() ||
    snapshot?.git?.branch ||
    snapshot?.repoBranch ||
    "<unresolved-target-branch>";
  return {
    remote,
    remoteUrl,
    branch,
    upstream: `${remote}/${branch}`,
  };
}

export async function dispatchAction(request: ActionRequest): Promise<ActionResponse> {
  if (window.__NDF_STANDALONE__) {
    const template = window.__NDF_ACTION_RESPONSES__?.[request.id];
    if (!template) {
      throw new Error(`standalone action template missing: ${request.id}`);
    }
    const topic =
      request.topic ||
      window.__NDF_SNAPSHOT__?.business?.focusedTopicId ||
      "<topic>";
    const episode =
      request.episode ||
      window.__NDF_SNAPSHOT__?.replay?.focused?.id ||
      "<episode>";
    const git = gitInputs(request);
    const replace = (value?: string | null) =>
      value
        ?.replaceAll("__NDF_HUMAN_INTENT__", request.intent?.trim() || "<human intent required>")
        .replaceAll("__NDF_TOPIC__", topic)
        .replaceAll("__NDF_EPISODE__", episode)
        .replaceAll("__NDF_REMOTE__", git.remote)
        .replaceAll("__NDF_REMOTE_URL__", git.remoteUrl)
        .replaceAll("__NDF_BRANCH__", git.branch)
        .replaceAll("__NDF_UPSTREAM_REF__", git.upstream);
    return {
      ...template,
      prompt: replace(template.prompt),
      path: replace(template.path),
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
