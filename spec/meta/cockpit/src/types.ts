export type DispatchKind = "composer" | "openFile" | "snapshot" | "projection_only";

export type EnabledAction = {
  enabled: boolean;
  reason: string | null;
  requiresIntent: boolean;
  dispatch: DispatchKind;
  failClosed: "disable" | "hide";
};

export type Snapshot = {
  schema: string;
  generatedAt?: string;
  repoHead?: string;
  snapshotSha?: string;
  payloadSha?: string;
  absorbedActionId?: string | null;
  projectionFreshness?: { state?: string; latest_action?: Record<string, unknown> };
  enabledActions?: Record<string, EnabledAction>;
  business?: {
    identity?: {
      name?: string;
      goal?: string;
      phase?: string;
      charterPath?: string;
      charterExists?: boolean;
      scales?: unknown[];
    };
    performance?: {
      goldenHeadStatus?: string;
      baselineId?: string;
      goldenSha?: string;
      warning?: string | null;
      scenes?: string[];
      aggQps?: number[];
    };
    topics?: TopicRow[];
    focusedTopic?: FocusedTopic | null;
    focusedTopicId?: string | null;
    proposals?: unknown[];
    nowNextBlocked?: { now?: string; next?: string; blocked?: number };
  };
  control?: {
    maturity?: string;
    genesis?: { accepted?: boolean; project_maturity?: string; kernel_installed?: boolean };
    kernelMap?: { seeds?: unknown[]; missing_seeds?: string[] };
    nextActions?: unknown[];
    metaGraph?: {
      checks?: Record<string, { state?: string; summary?: string }>;
      findings?: Array<{ kind?: string; severity?: string; why_blocked?: string }>;
    };
    processHop?: {
      focusedPath?: string;
      title?: string;
      hop?: string;
      nextHumanPhrase?: string;
    } | null;
    processProposals?: unknown[];
    processProposalArchivedCount?: number;
  };
  runtime?: Record<string, unknown>;
  replay?: {
    episodes?: HopRow[];
    focused?: FocusedHop | null;
    omittedCount?: number;
  };
};

export type TopicRow = {
  id: string;
  lifecycle?: string;
  hypothesis?: string;
  surface?: string[];
  baseline?: string;
  blockers?: string[];
};

export type FocusedTopic = TopicRow & {
  topicOverview?: Record<string, unknown>;
  spaces?: Record<string, { ready?: boolean; gaps?: string[]; purpose?: string }>;
  decision?: { selected?: string | null; offered?: string[]; state?: string };
  health?: { findings?: Array<{ kind?: string; space?: string; why_blocked?: string; clause_refs?: unknown }> };
  delegation?: {
    static_preflight_passed?: boolean;
    runtime_dispatch_ready?: boolean;
    context_plan?: { role?: string; plan_sha?: string; read_count?: number };
  };
};

export type HopRow = {
  id: string;
  title?: string;
  plane?: string;
  agent?: string;
  happenedAt?: string;
  topic?: string;
  canRestoreRecord?: boolean;
};

export type FocusedHop = HopRow & {
  humanUtterance?: string;
  assembledPrompt?: { text?: string; whyMissing?: string };
  dispatchedPrompt?: { text?: string; whyMissing?: string };
  timeline?: Array<{ seq?: number; kind?: string; title?: string }>;
  promptDrift?: { mismatch?: boolean };
};

export type TabId = "product" | "topics" | "control" | "agents" | "replay";
