import type { FocusedTopic, Snapshot } from "./types";
import type { PhaseId, PhaseState } from "./phaseMap";

export type ReadyCheck = {
  id: string;
  label: string;
  ok: boolean;
  detail: string;
  /** Existing registry action id, or "human-phrase" projection jump into gate Human zone. */
  fix?: string | null;
  fixPhase?: PhaseId | null;
  /** When true, run fix from hero panel without switching selectedActionId. */
  fixInline?: boolean;
  /** Human hint when check failed but no fix action (e.g. prerequisite missing). */
  hint?: string | null;
};

export type FaceStatus = {
  id: string;
  label: string;
  present: boolean;
};

export type Readiness = {
  safe: boolean;
  checks: ReadyCheck[];
  faces: FaceStatus[];
  blockers: string[];
};

const FACE_ORDER = [
  { id: "topic", label: "TOPIC.md" },
  { id: "design", label: "DESIGN.md" },
  { id: "perf_baseline", label: "PERF_BASELINE.md" },
  { id: "delta", label: "DELTA.md" },
  { id: "interface", label: "INTERFACE.md" },
  { id: "commits", label: "COMMITS.md" },
];

export function buildReadiness(focused: FocusedTopic | null | undefined): Readiness {
  if (!focused) {
    return { safe: false, checks: [], faces: [], blockers: ["no_focused_topic"] };
  }
  const d = focused.delegation || {};
  const gates = focused.controlPipelines?.gate?.checklist || [];
  const binder = focused.controlPipelines?.binder?.checklist || [];
  const spaces = focused.spaces || {};
  const blockers = d.dispatch_blockers || [];

  const selectedDecision = focused.decision?.selected;
  const dispatchChipOk =
    selectedDecision === "implement" || selectedDecision === "continue_exploring";

  let runtimeDetail = d.runtime_dispatch_ready
    ? "ready"
    : "runtime not probed / lease not ready";
  let runtimeFix: string | null = null;
  let runtimeInline = false;
  let runtimeHint: string | null = null;
  if (!d.runtime_dispatch_ready) {
    if (!dispatchChipOk) {
      runtimeHint =
        focused.decision?.decision_required
          ? "先点上方探索决策芯片（implement 或 continue_exploring），再准备 ACP 租约"
          : "TOPIC 须写入 selected_decision=implement 或 continue_exploring";
    } else {
      runtimeFix = "prepare-acp-lease";
      runtimeInline = true;
    }
  }

  const leasePresent = Boolean(
    focused.agentRun?.run_id && focused.agentRun?.worktree,
  );
  let leaseFix: string | null = null;
  let leaseInline = false;
  let leaseHint: string | null = null;
  if (!leasePresent) {
    if (!dispatchChipOk) {
      leaseHint =
        focused.decision?.decision_required
          ? "先点上方探索决策芯片（implement 或 continue_exploring），再准备 ACP 租约"
          : "TOPIC 须写入 selected_decision=implement 或 continue_exploring";
    } else {
      leaseFix = "prepare-acp-lease";
      leaseInline = true;
    }
  }

  const gateValid = (id: string) =>
    gates.find((g) => g.id === id)?.state === "valid";

  const faces: FaceStatus[] = FACE_ORDER.map((face) => {
    const row = binder.find((b) => b.id === face.id);
    return {
      id: face.id,
      label: face.label,
      present: row?.exists === true,
    };
  });

  const checks: ReadyCheck[] = [
    {
      id: "lifecycle",
      label: "主题仍 exploring",
      ok: focused.lifecycle === "exploring" || focused.lifecycle === "closing",
      detail: focused.lifecycle || "unknown",
      fix: focused.lifecycle === "exploring" ? null : "diagnose-topic",
      fixPhase: "execute",
      fixInline: focused.lifecycle !== "exploring",
    },
    {
      id: "topic_review",
      label: "TOPIC已审核",
      ok: gateValid("topic_review"),
      detail: gates.find((g) => g.id === "topic_review")?.state || "missing",
      fix: gateValid("topic_review") ? null : "human-phrase",
      fixPhase: "gate",
    },
    {
      id: "design_review",
      label: "DESIGN已审核",
      ok: gateValid("design_review"),
      detail: gates.find((g) => g.id === "design_review")?.state || "missing",
      fix: gateValid("design_review") ? null : "human-phrase",
      fixPhase: "gate",
    },
    {
      id: "implementation_approval",
      label: "可以开始实现",
      ok: gateValid("implementation_approval"),
      detail: gates.find((g) => g.id === "implementation_approval")?.state || "missing",
      fix: gateValid("implementation_approval") ? null : "human-phrase",
      fixPhase: "gate",
    },
    {
      id: "faces",
      label: "装订六面齐全",
      ok: faces.every((f) => f.present),
      detail: `${faces.filter((f) => f.present).length}/6`,
      fix: faces.every((f) => f.present) ? null : "binder-pipeline",
      fixPhase: "bind",
    },
    {
      id: "spaces",
      label: "三空间 ready",
      ok: ["design", "implementation", "test"].every((k) => spaces[k]?.ready === true),
      detail: ["design", "implementation", "test"]
        .map((k) => `${k}:${spaces[k]?.ready ? "ok" : "gap"}`)
        .join(" · "),
      fix:
        spaces.design?.ready === false
          ? null
          : spaces.implementation?.ready === false
            ? "poc-prepare-baseline"
            : spaces.test?.ready === false
              ? "poc-measurement"
              : null,
      fixPhase:
        spaces.design?.ready === false
          ? null
          : spaces.implementation?.ready === false
            ? "bind"
            : spaces.test?.ready === false
              ? "execute"
              : null,
    },
    {
      id: "static_preflight",
      label: "静态预检",
      ok: d.static_preflight_passed === true,
      detail: d.static_preflight_passed ? "passed" : blockers.join(", ") || "failed",
      fix: d.static_preflight_passed ? null : "diagnose-topic",
      fixPhase: "execute",
      fixInline: !d.static_preflight_passed,
    },
    {
      id: "context_verify",
      label: "机械上下文校验",
      ok: d.context_verify?.valid !== false,
      detail: d.context_plan?.plan_sha?.slice(0, 12) || "no plan",
      fix: d.context_verify?.valid === false ? "refresh-topic" : null,
      fixPhase: "execute",
      fixInline: d.context_verify?.valid === false,
    },
    {
      id: "runtime_dispatch",
      label: "运行时可派发",
      ok: d.runtime_dispatch_ready === true,
      detail: runtimeDetail,
      fix: runtimeFix,
      fixPhase: "execute",
      fixInline: runtimeInline,
      hint: runtimeHint,
    },
    {
      id: "runtime_lease",
      label: "ACP 隔离租约",
      ok: leasePresent,
      detail: leasePresent
        ? `run ${String(focused.agentRun?.run_id || "").slice(0, 24)}`
        : "jsonl 无活跃隔离 worktree / run_id",
      fix: leaseFix,
      fixPhase: "execute",
      fixInline: leaseInline,
      hint: leaseHint,
    },
  ];

  const safe = d.safe_to_dispatch === true;
  return { safe, checks, faces, blockers };
}

export function derivePhaseStates(focused: FocusedTopic | null | undefined): Record<PhaseId, PhaseState> {
  const readiness = buildReadiness(focused);
  const facesOk = readiness.faces.length > 0 && readiness.faces.every((f) => f.present);
  const designPresent = readiness.faces.find((f) => f.id === "design")?.present === true;
  const gates = focused?.controlPipelines?.gate?.checklist || [];
  const gatesOk = gates.length > 0 && gates.every((g) => g.state === "valid");
  const lifecycle = focused?.lifecycle || "";
  const binderNeeded = focused?.controlPipelines?.binder?.needed === true;
  const dispatchFailed =
    focused?.agentRun?.dispatch_state === "failed" ||
    focused?.agentRun?.completion_rejected === true;
  const dispatchInflight =
    focused?.agentRun?.dispatch_state === "sent" ||
    focused?.agentRun?.dispatch_state === "awaiting_result";

  const explore: PhaseState = designPresent ? "done" : "active";
  const bind: PhaseState =
    dispatchFailed || dispatchInflight
      ? facesOk
        ? "done"
        : "pending"
      : !designPresent
        ? "blocked"
        : facesOk && !binderNeeded
          ? "done"
          : "active";
  const gate: PhaseState = !facesOk
    ? "blocked"
    : gatesOk
      ? "done"
      : dispatchFailed || dispatchInflight
        ? "pending"
        : "active";
  let execute: PhaseState = "pending";
  if (!gatesOk) execute = "blocked";
  else if (lifecycle === "exploring" || lifecycle === "closing") execute = "active";
  else if (lifecycle === "promoted" || lifecycle === "rejected") execute = "done";

  let promote: PhaseState = "pending";
  if (lifecycle === "closing") promote = "active";
  else if (lifecycle === "promoted" || lifecycle === "rejected") promote = "done";
  else if (!gatesOk) promote = "pending";
  else if (lifecycle === "exploring") promote = "active";

  return { explore, bind, gate, execute, promote };
}

export function activePhaseFromStates(states: Record<PhaseId, PhaseState>): PhaseId {
  const order: PhaseId[] = ["explore", "bind", "gate", "execute", "promote"];
  const active = order.find((p) => states[p] === "active");
  if (active) return active;
  const blocked = order.find((p) => states[p] === "blocked");
  if (blocked) return blocked;
  return "execute";
}

export function exploreTrackPhases(focused: FocusedTopic | null | undefined, topicRowBaseline?: string): Array<{ id: PhaseId; st: PhaseState }> {
  const states = derivePhaseStates(focused);
  // When we only have a topic row (not focused), approximate from blockers/baseline.
  if (!focused && topicRowBaseline != null) {
    return [
      { id: "explore", st: "done" },
      { id: "bind", st: topicRowBaseline === "y" || topicRowBaseline === "current" ? "done" : "active" },
      { id: "gate", st: "pending" },
      { id: "execute", st: "pending" },
      { id: "promote", st: "pending" },
    ];
  }
  return (["explore", "bind", "gate", "execute", "promote"] as PhaseId[]).map((id) => ({
    id,
    st: states[id],
  }));
}

export function topicGapCount(snapshot: Snapshot, topicId: string): number {
  const focused = snapshot.business?.focusedTopic;
  if (focused?.id === topicId) {
    const r = buildReadiness(focused);
    return r.checks.filter((c) => !c.ok).length + r.faces.filter((f) => !f.present).length;
  }
  const row = (snapshot.business?.topics || []).find((t) => t.id === topicId);
  return row?.blockers?.length || 0;
}
