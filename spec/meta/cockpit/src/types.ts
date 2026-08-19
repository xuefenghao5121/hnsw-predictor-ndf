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
      scales?: Array<[string, string]>;
    };
    performance?: {
      goldenHeadStatus?: string;
      baselineId?: string;
      goldenSha?: string;
      warning?: string | null;
      scenes?: string[];
      aggQps?: number[];
      steadyQps?: number[];
      recall?: string[];
    };
    capabilities?: Array<[string, number, number, number, string]>;
    topics?: TopicRow[];
    focusedTopic?: FocusedTopic | null;
    focusedTopicId?: string | null;
    proposals?: Array<[string, string, string]>;
    roadmap?: Array<[string, string, string, string, string]>;
    risks?: Array<{ kind?: string; severity?: string; message?: string; path?: string }>;
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
  topicOverview?: {
    purpose?: string;
    hypothesis?: string;
    explore_surface?: string[];
    idea_sources?: { depends_on_topics?: string[]; proposal_paths?: string[] };
    lifecycle?: string;
  };
  spaces?: Record<string, {
    ready?: boolean;
    gaps?: string[];
    purpose?: string;
    clause_refs?: Array<{ id?: string; title?: string }>;
    latest_round?: string;
    latest_verdict?: string;
    delta_path?: string;
  }>;
  decision?: {
    selected?: string | null;
    offered?: string[];
    state?: string;
    blocked?: Record<string, string>;
    meanings?: Record<string, string>;
    briefing?: { verdict?: string; latest_round?: string; latest_round_row?: string };
  };
  health?: {
    findings?: Array<{
      kind?: string;
      severity?: string;
      space?: string;
      why_blocked?: string;
      clause_refs?: Array<{ id?: string; title?: string }>;
      repair_owner?: string;
      repair_task?: string;
      allowed_write_root?: string;
    }>;
    checks?: Record<string, { state?: string; summary?: string }>;
    next_actions?: Array<{
      label?: string;
      owner?: string;
      task?: string;
      space?: string;
      allowed_write_root?: string;
    }>;
  };
  ndfFoundation?: {
    stable_summary?: Record<string, number>;
    explore_surface_bind?: Array<{ surface?: string; clauses?: unknown[] }>;
    depends_on_edges?: unknown[];
    clause_count?: number;
  };
  workflowMeta?: {
    note?: string;
    spec_health_state?: string;
    spec_health_checks?: Record<string, string>;
    node_count?: number;
  };
  traceability?: Array<{
    goal_or_clause?: string;
    design?: string;
    code_or_commit?: string;
    verification?: string;
  }>;
  delegation?: {
    safe_to_dispatch?: boolean;
    static_preflight_passed?: boolean;
    runtime_dispatch_ready?: boolean;
    context_plan?: { role?: string; plan_sha?: string; read_count?: number };
    context_verify?: { valid?: boolean; errors?: Array<{ kind?: string; message?: string }> };
    dispatch_blockers?: string[];
    evaluated_at?: string;
  };
  controlPipelines?: Record<string, {
    label?: string;
    needed?: boolean;
    step_count?: number;
    dispatch?: { state?: string; acknowledged?: boolean; blockers?: string[] };
  }>;
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
