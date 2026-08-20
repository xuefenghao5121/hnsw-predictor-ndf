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
  repoBranch?: string;
  repoRemote?: string;
  repoRemoteUrl?: string;
  repoUpstream?: string;
  git?: {
    remote?: string;
    remoteUrl?: string;
    branch?: string;
    upstreamRef?: string;
    head?: string;
  };
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
    genesis?: {
      accepted?: boolean;
      project_maturity?: string;
      kernel_installed?: boolean;
      install_needed?: boolean;
      genesis_trunk_sha?: string;
      mode?: string | null;
    };
    kernelMap?: {
      seeds?: Array<{ id?: string; title?: string; status?: string; role?: string; scope?: string }>;
      missing_seeds?: string[];
      missingSeeds?: string[];
      stable_summary?: Record<string, number>;
    };
    nextActions?: Array<{
      kind?: string;
      label?: string;
      owner?: string;
      task?: string;
      space?: string;
      allowed_write_root?: string;
    }>;
    metaGraph?: {
      checks?: Record<string, { state?: string; summary?: string }>;
      findings?: Array<{
        kind?: string;
        severity?: string;
        why_blocked?: string;
        space?: string;
        repair_owner?: string;
        repair_task?: string;
        allowed_write_root?: string;
        plane?: string;
      }>;
    };
    processHop?: {
      focusedPath?: string;
      title?: string;
      hop?: string;
      nextHumanPhrase?: string;
    } | null;
    processProposals?: Array<[string, string, string]>;
    processProposalArchivedCount?: number;
    legacyUnknownTopics?: string[];
    invalidatedReceipts?: string[];
    proposalPlaneWarnings?: Array<[string, string, string]>;
    draftMapWarnings?: Array<[string, string, string]>;
  };
  runtime?: {
    implementation?: {
      provider?: string;
      status?: string;
      pipelineReachable?: boolean | null;
      defaultSession?: string;
      activeRuns?: unknown[];
      cliAvailable?: boolean | null;
      doctorOk?: boolean | null;
      resumeAvailable?: boolean | null;
      configuredSessionVisible?: boolean | null;
      probeError?: string | null;
      probeNote?: string | null;
      workspace?: RuntimeWorkspace;
    };
    control?: {
      provider?: string;
      defaultSessionKey?: string;
      reachable?: boolean | null;
      configuredSessionVisible?: boolean | null;
      probe?: unknown;
      workspace?: RuntimeWorkspace;
    };
  };
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
    summary?: string;
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
    dispatch?: { state?: string; acknowledged?: boolean; blockers?: string[]; request_id?: string; episode_id?: string };
    handoff?: { blocked_gate?: string; next_binder_facet?: string; next_binder_label?: string };
    handoff_from_gate?: { blocked_gate?: string; next_binder_facet?: string; next_binder_label?: string };
    blocked_by_binder?: boolean;
    decision_required?: boolean;
  }>;
  agentRun?: {
    provider?: string;
    status?: string;
    run_id?: string | null;
    session_id?: string | null;
    base_sha?: string | null;
    worktree?: string | null;
  };
  commandEntry?: { nextStepLine?: string; decisionRequired?: boolean };
};

export type HopRow = {
  id: string;
  title?: string;
  plane?: string;
  agent?: string;
  happenedAt?: string;
  topic?: string;
  task?: string;
  resultLine?: string | null;
  actor?: string;
  participants?: string[];
  kinds?: string[];
  lenses?: ReplayAgentLens[];
  canRestoreRecord?: boolean;
};

export type FocusedHop = HopRow & {
  humanUtterance?: string;
  assembledPrompt?: { text?: string; whyMissing?: string };
  dispatchedPrompt?: { text?: string; whyMissing?: string };
  timeline?: Array<{
    seq?: number;
    kind?: string;
    title?: string;
    plane?: string;
    space?: string;
    actor?: string;
    agent?: string;
    lenses?: ReplayAgentLens[];
    payloadPreview?: string;
  }>;
  promptDrift?: { mismatch?: boolean };
  dispatchLeak?: boolean | Record<string, unknown>;
  assembledContext?: { orderedReads?: unknown[] };
  readWhyMissing?: string;
};

export type TabId = "product" | "topics" | "control" | "agents" | "replay";
export type ReplayPlane = "all" | "project" | "meta";
export type ReplayAgentLens = "all" | "command-agent" | "openclaw" | "claude-code" | "context-compiler";

export type RuntimeWorkspace = {
  binding?: { repoRoot?: string; statePath?: string; activeTopic?: string | null };
  stateExists?: boolean;
  match?: boolean | null;
  state?: string;
};
