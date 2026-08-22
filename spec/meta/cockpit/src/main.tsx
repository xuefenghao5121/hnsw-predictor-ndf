import {
  Component,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ErrorInfo,
  type ReactNode,
} from "react";
import { createRoot } from "react-dom/client";
import { ActionButton } from "./ActionButton";
import { ActionCard, HumanPhraseCard } from "./ActionCard";
import { CloseDecisionChips } from "./CloseDecisionChips";
import { dispatchAction, isStandaloneCommander, loadSnapshot, watchLiveSnapshot } from "./api";
import { GoldenPerformance } from "./charts/GoldenPerformance";
import { TopicOverview } from "./charts/TopicOverview";
import { requireAction } from "./catalog";
import {
  ACTION_PHASE,
  GLOBAL_SIDEBAR_ACTIONS,
  HERO_ACTION_ID,
  PHASES,
  providerKind,
  providerLabel,
  sidebarActionsForPhase,
  type PhaseId,
} from "./phaseMap";
import {
  activePhaseFromStates,
  buildReadiness,
  derivePhaseStates,
  exploreTrackPhases,
  type ReadyCheck,
} from "./readiness";
import { buildOverviewProposalPrompt, colorizePrompt } from "./promptColor";
import type {
  EnabledAction,
  FocusedTopic,
  ModuleId,
  ProjPlane,
  ReplayAgentLens,
  Snapshot,
} from "./types";
import "./styles.css";

function enabledOf(snapshot: Snapshot | null, id: string): EnabledAction | undefined {
  return snapshot?.enabledActions?.[id];
}

const ACTION_WHY: Record<string, string> = {
  "design-prepare": "把已冻结提案展开为 DESIGN contract",
  "poc-prepare-baseline": "建立隔离 worktree 与基线工作区",
  "binder-pipeline": "补齐六面：TOPIC/DESIGN/PERF/DELTA/INTERFACE/COMMITS",
  "binder-amend": "不改变既有假设的增量装订修订",
  "gate-pipeline": "推进三闸审计（不替代人工口令）",
  "delegate-poc": "实现已批准的 DESIGN/INTERFACE，作为 POC 轮",
  "poc-measurement": "同 TOPIC/DESIGN 再开一轮 DELTA（continue_exploring）",
  "poc-isolation-repair": "修复 POC 写入隔离检查的缺口",
  "diagnose-topic": "inspect → repair → refresh 的检查入口",
  "open-delta": "在本地编辑器查看变化账本",
  "prepare-acp-lease": "准备 ACP 租约 / 探测实现管道",
  "generate-next-step": "用决策芯片生成下一跳（非自由意图）",
  "next-close-hop": "推进 closing → promoted 编排",
  "align-golden": "重跑 Golden 矩阵并绑定新 Trunk SHA",
  "refresh-snapshot": "重建工作流投影数据",
  "refresh-topic": "刷新当前 TOPIC 投影",
  "command-replay-run": "重放一次历史 hop",
  "command-replay-compare": "对照回放结果",
};

const DECISION_LABELS: Record<string, string> = {
  implement: "首次按设计实现",
  continue_exploring: "同契约再开一轮",
  amend: "修订装订",
  promote: "晋升合入",
  partial: "部分晋升",
  reject: "负结果关闭",
};

const EXECUTE_DECISION_ORDER = ["implement", "continue_exploring", "amend"] as const;

const INLINE_HERO_FIXES = new Set([
  "prepare-acp-lease",
  "diagnose-topic",
  "refresh-topic",
  "poc-isolation-repair",
  "open-delta",
]);

function isLeaseStubHop(agentRun: FocusedTopic["agentRun"] | null | undefined): boolean {
  if (!agentRun) return false;
  const summary = String(agentRun.result_summary || "");
  if (
    summary === "lease_only_no_implementation_start" ||
    summary.endsWith("_no_implementation_start")
  ) {
    return true;
  }
  return agentRun.dispatch_state === "succeeded" && !agentRun.worktree;
}

function hopStatusLine(agentRun: FocusedTopic["agentRun"] | null | undefined): string {
  if (agentRun?.completion_rejected) {
    return "运输已送达，回执未验收";
  }
  if (["sent", "awaiting_result"].includes(agentRun?.dispatch_state || "")) {
    return "在途 · 本聊天回「进展如何」";
  }
  if (agentRun?.dispatch_state === "failed") {
    return "上次 hop 失败";
  }
  if (agentRun?.dispatch_state === "succeeded") {
    if (isLeaseStubHop(agentRun)) {
      return "运输结束，租约未落地";
    }
    return "上次 hop 已验收";
  }
  return "未发出";
}

function humanFixBlockedReason(actionId: string, reason: string | null | undefined): string {
  const r = reason || "disabled";
  if (r.includes("selectedImplementOrExplore")) {
    return "须先选探索决策芯片（implement 或 continue_exploring），再准备 ACP 租约";
  }
  if (r.includes("fresh")) {
    return "快照过期，请先刷新 snapshot";
  }
  if (actionId === "prepare-acp-lease" && r.includes("runtimeNotReady")) {
    return "运行时已就绪，无需准备租约";
  }
  if (actionId === "prepare-acp-lease" && r.includes("missingActiveLease")) {
    return "已有活跃隔离租约，无需再准备";
  }
  return r;
}

function workbenchComposeBody(
  phase: PhaseId,
  selectedActionId: string,
  focused: FocusedTopic,
  selectedAction: { clauseRefs?: string[] } | null,
  snapshot: Snapshot | null,
): string {
  if (
    phase === "execute" &&
    selectedActionId === HERO_ACTION_ID &&
    focused.commandEntry?.nextStepLine
  ) {
    return [
      "# 下一步",
      focused.commandEntry.nextStepLine,
      "",
      "## 冻结契约（摘要）",
      `topic: ${focused.id}`,
      `scope: poc/${focused.id}/`,
      `clauses: ${(selectedAction?.clauseRefs || []).map((c) => `[[${c}]]`).join(" ")}`,
      `HEAD: ${snapshot?.repoHead || ""}`,
      "",
      "派发 Prompt 仅在点击底部「派发」时弹出；此处不重复 Command Agent 全文。",
    ].join("\n");
  }
  return [
    "# 任务契约（已冻结）",
    `topic: ${focused.id}`,
    `action: ${selectedActionId || "—"}`,
    `scope: poc/${focused.id}/`,
    `DESIGN §2 / INTERFACE — 见装订器`,
    `clauses: ${(selectedAction?.clauseRefs || []).map((c) => `[[${c}]]`).join(" ")}`,
    `HEAD: ${snapshot?.repoHead || ""}`,
    "",
    "## 说明",
    focused.commandEntry?.nextStepLine || "从左侧选择动作；契约由装订器机械编译。",
    "",
    "Composer Prompt 仅在点击派发时弹出，不在工作台常驻全文。",
  ].join("\n");
}

class ErrorBoundary extends Component<{ children: ReactNode }, { message: string | null }> {
  state = { message: null as string | null };

  static getDerivedStateFromError(error: Error) {
    return { message: error.message || "render failed" };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("NDF commander render failed", error, info.componentStack);
  }

  render() {
    if (this.state.message) {
      return <div className="banner">页面加载出错：{this.state.message}</div>;
    }
    return this.props.children;
  }
}

function shortSha(sha?: string | null, n = 7): string {
  return sha ? sha.slice(0, n) : "—";
}

function App() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [module, setModule] = useState<ModuleId>("overview");
  const [plane, setPlane] = useState<ProjPlane>("product");
  const [phase, setPhase] = useState<PhaseId>("execute");
  const [selectedActionId, setSelectedActionId] = useState<string>(HERO_ACTION_ID);
  const [humanZoneFocus, setHumanZoneFocus] = useState(false);
  const [productIntent, setProductIntent] = useState("");
  const [intentWarn, setIntentWarn] = useState(false);
  const [proposalPrompt, setProposalPrompt] = useState<string | null>(null);
  const [showActs, setShowActs] = useState(false);
  const [showProj, setShowProj] = useState(false);
  const [selectedTopic, setSelectedTopic] = useState<string>("");
  const [selectedHop, setSelectedHop] = useState<string>("");
  const [dialog, setDialog] = useState<{
    title: string;
    body: string;
    hint?: string;
    kind?: "composer" | "openFile";
  } | null>(null);
  const [copied, setCopied] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [remoteName, setRemoteName] = useState("origin");
  const [remoteUrl, setRemoteUrl] = useState("");
  const [remoteBranch, setRemoteBranch] = useState("");
  const [composePrompt, setComposePrompt] = useState<string>("");
  const [promptActionId, setPromptActionId] = useState<string>("");
  const live = !isStandaloneCommander();
  const snapshotRef = useRef<Snapshot | null>(null);
  const gitRef = useRef({ remoteName, remoteUrl, remoteBranch });
  const dialogRef = useRef<HTMLDivElement | null>(null);
  snapshotRef.current = snapshot;
  gitRef.current = { remoteName, remoteUrl, remoteBranch };

  const applySnapshot = useCallback((data: Snapshot, mode: "full" | "live") => {
    const previous = snapshotRef.current;
    if (mode === "live" && previous?.payloadSha && previous.payloadSha === data.payloadSha) {
      return;
    }
    setError(null);
    setSnapshot(data);
    if (mode === "full") {
      setRemoteName(data.git?.remote || data.repoRemote || "origin");
      setRemoteUrl(data.git?.remoteUrl || data.repoRemoteUrl || "");
      setRemoteBranch(data.git?.branch || data.repoBranch || "");
    } else {
      const draft = gitRef.current;
      const prevRemote = previous?.git?.remote || previous?.repoRemote || "origin";
      const prevUrl = previous?.git?.remoteUrl || previous?.repoRemoteUrl || "";
      const prevBranch = previous?.git?.branch || previous?.repoBranch || "";
      if (draft.remoteName === prevRemote) {
        setRemoteName(data.git?.remote || data.repoRemote || draft.remoteName);
      }
      if (draft.remoteUrl === prevUrl) {
        setRemoteUrl(data.git?.remoteUrl || data.repoRemoteUrl || "");
      }
      if (draft.remoteBranch === prevBranch) {
        setRemoteBranch(data.git?.branch || data.repoBranch || "");
      }
    }
    if (data.business?.identity?.charterExists === false) {
      setPlane("control");
    }
    const focused = data.business?.focusedTopicId;
    if (focused) setSelectedTopic(focused);
    const hop = data.replay?.focused?.id;
    if (hop) setSelectedHop(hop);
  }, []);

  const refresh = useCallback(
    async (mode: "full" | "live" = "full") => {
      try {
        const data = await loadSnapshot();
        applySnapshot(data, mode);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    },
    [applySnapshot],
  );

  useEffect(() => {
    void refresh("full");
  }, [refresh]);

  useEffect(() => {
    if (!live) return undefined;
    return watchLiveSnapshot((sha) => {
      if (snapshotRef.current?.payloadSha === sha) return;
      void refresh("live");
    });
  }, [live, refresh]);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(null), 2400);
  }, []);

  const run = useCallback(
    async (
      id: string,
      extra?: {
        intent?: string;
        topic?: string;
        episode?: string;
        timelineStep?: number;
        probeMode?: "light" | "full";
      },
    ) => {
      const action = requireAction(id);
      if (action.dispatch === "projection_only") return;
      setBusyAction(id);
      try {
        const result = await dispatchAction({
          id,
          remote: remoteName,
          remoteUrl,
          branch: remoteBranch,
          topic: extra?.topic || selectedTopic || undefined,
          ...extra,
        });
        if (result.snapshot) {
          setSnapshot(result.snapshot);
          setError(null);
        }
        if (result.prompt) {
          setCopied(false);
          setComposePrompt(result.prompt);
          setPromptActionId(id);
          const kind = providerKind(action);
          const delegateHint =
            kind === "claude-code"
              ? "将委派 Claude Code ACP（独立 worktree/branch）"
              : kind === "openclaw"
                ? "将委派 OpenClaw Control"
                : "本按钮不自动委派工作者";
          setDialog({
            title: `复制委派 Prompt · 不自动执行 · ${action.label} · ${remoteName}/${remoteBranch || "unspecified-branch"}`,
            hint:
              `${delegateHint}。粘贴到 Command Agent 后只组 pack；` +
              `safe_to_dispatch 时 afterShellExecution hook 发出并等到回执后 action-commit + snapshot。` +
              `按钮本身不派工；sent/acknowledged 不是 validated completion。`,
            body: result.prompt,
            kind: "composer",
          });
        } else if (result.path) {
          setCopied(false);
          setDialog({
            title: `本按钮只打开文件，不派 Agent · ${action.label}`,
            hint: "在编辑器中打开下列路径；不生成 Composer 委派 Prompt。",
            body: result.path,
            kind: "openFile",
          });
        } else if (result.humanPhrase) {
          showToast(`人口令投影：${result.humanPhrase}`);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setBusyAction(null);
      }
    },
    [remoteBranch, remoteName, remoteUrl, selectedTopic, showToast],
  );

  const topics = snapshot?.business?.topics || [];
  const hops = snapshot?.replay?.episodes || [];
  const focused = snapshot?.business?.focusedTopic;
  const freshness = snapshot?.projectionFreshness?.state || "unknown";
  const readiness = useMemo(() => buildReadiness(focused), [focused]);
  const phaseStates = useMemo(() => derivePhaseStates(focused), [focused]);

  useEffect(() => {
    if (module !== "workbench" || !focused) return;
    setPhase(activePhaseFromStates(phaseStates));
  }, [focused?.id, module]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (module !== "workbench") return;
    setComposePrompt("");
    setPromptActionId("");
  }, [phase, selectedActionId, humanZoneFocus, module]);

  useEffect(() => {
    if (module !== "workbench") return;
    if (phase === "execute") {
      setSelectedActionId(HERO_ACTION_ID);
      setHumanZoneFocus(false);
      return;
    }
    if (phase === "gate") {
      setSelectedActionId("gate-pipeline");
      setHumanZoneFocus(false);
      return;
    }
    if (phase === "explore") {
      setSelectedActionId("");
      setHumanZoneFocus(false);
      return;
    }
    const first = sidebarActionsForPhase(phase)[0];
    if (first) {
      setSelectedActionId(first);
      setHumanZoneFocus(false);
    } else {
      setSelectedActionId("");
    }
  }, [phase, module]);

  const enterWorkbench = useCallback(
    async (topicId: string) => {
      setSelectedTopic(topicId);
      setModule("workbench");
      setShowActs(false);
      setShowProj(false);
      setPlane("product");
      const needFocus = snapshot?.business?.focusedTopicId !== topicId;
      // Already focused: pure UI navigation — do not emit snapshot Prompt dialog.
      if (!needFocus) return;
      await run("open-workbench", { topic: topicId });
    },
    [run, snapshot?.business?.focusedTopicId],
  );

  const jumpTo = useCallback(
    (fix: string, fixPhase?: PhaseId | null) => {
      if (fixPhase) setPhase(fixPhase);
      if (fix === "human-phrase") {
        setHumanZoneFocus(true);
        setSelectedActionId("gate-pipeline");
        setPhase("gate");
        return;
      }
      setHumanZoneFocus(false);
      setSelectedActionId(fix);
      const mapped = ACTION_PHASE[fix];
      if (mapped && mapped !== "_all") setPhase(mapped);
    },
    [],
  );

  const handleReadyFix = useCallback(
    (check: ReadyCheck) => {
      if (!check.fix) return;
      if (check.fixInline || INLINE_HERO_FIXES.has(check.fix)) {
        const en = enabledOf(snapshot, check.fix);
        if (en?.enabled !== true) {
          showToast(
            `fail-closed：${humanFixBlockedReason(check.fix, en?.reason)}`,
          );
          return;
        }
        void run(check.fix);
        return;
      }
      jumpTo(check.fix, check.fixPhase);
    },
    [jumpTo, run, showToast, snapshot],
  );

  const copyText = useCallback(
    async (text: string) => {
      try {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        showToast("已复制到剪贴板");
      } catch {
        setError("clipboard write failed");
      }
    },
    [showToast],
  );

  const genProposal = useCallback(() => {
    const intent = productIntent.trim();
    if (!intent) {
      setIntentWarn(true);
      setProposalPrompt(null);
      return;
    }
    setIntentWarn(false);
    setProposalPrompt(buildOverviewProposalPrompt(intent, snapshot?.repoHead));
  }, [productIntent, snapshot?.repoHead]);

  const dispatchSelected = useCallback(async () => {
    if (humanZoneFocus) {
      showToast("人口令须由人在会话中发出；请复制下方口令，不要用 Agent 代写");
      return;
    }
    const id = selectedActionId;
    const action = requireAction(id);
    const en = enabledOf(snapshot, id);
    if (en?.enabled !== true) {
      showToast(`fail-closed：${id} 不可用（${en?.reason || "disabled"}）`);
      return;
    }
    if (action.requiresIntent) {
      showToast("该动作需要决策芯片，请先点选 Decision 芯片");
      return;
    }
    await run(id);
  }, [humanZoneFocus, run, selectedActionId, showToast, snapshot]);

  useEffect(() => {
    if (!dialog) return;
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") setDialog(null);
    };
    window.addEventListener("keydown", onKey);
    dialogRef.current?.querySelector<HTMLElement>("button, [href], textarea")?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [dialog]);

  const exploringTopics = topics.filter(
    (t) => t.lifecycle === "exploring" || t.lifecycle === "closing",
  );
  const promoteRows = (snapshot?.business?.roadmap || []).slice(0, 6);
  const gateChecklist = focused?.controlPipelines?.gate?.checklist || [];
  const awaitingGates = gateChecklist.filter((g) => g.state !== "valid");
  const selectedAction = selectedActionId ? requireAction(selectedActionId) : null;
  const selectedEnabled = enabledOf(snapshot, selectedActionId);
  const heroEnabled =
    selectedActionId === HERO_ACTION_ID
      ? enabledOf(snapshot, HERO_ACTION_ID)?.enabled === true && readiness.safe
      : selectedEnabled?.enabled === true && !humanZoneFocus;

  const hasIsolationFinding = (focused?.health?.findings || []).some((f) => {
    const kind = String(f.kind || "");
    return kind.includes("isolation") || kind === "trunk_write" || kind === "poc_isolation";
  });

  const globalSidebarActions = GLOBAL_SIDEBAR_ACTIONS.filter(
    (id) => requireAction(id).commanderSurface !== false,
  );
  const phaseSidebarActions = sidebarActionsForPhase(phase);
  const sidebarActionCount =
    (phase === "execute" ? 1 : phaseSidebarActions.length) + globalSidebarActions.length;

  const agentCards = useMemo(() => buildAgentCards(snapshot, focused, freshness), [snapshot, focused, freshness]);

  const rootClass = [
    "app-root",
    module === "overview" ? "mod-overview" : "mod-workbench",
    showActs ? "show-acts" : "",
    showProj ? "show-proj" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={rootClass}>
      <header className="topbar">
        <div className="brand">
          NDF Commander <span className="v">v3.1</span>
        </div>
        <div className="planes" role="group" aria-label="模块切换" id="modSwitch">
          <button
            type="button"
            data-module="overview"
            data-ndf-action="mod-overview"
            aria-pressed={module === "overview"}
            onClick={() => setModule("overview")}
          >
            Overview · 全局
          </button>
          <button
            type="button"
            data-module="workbench"
            data-ndf-action="mod-workbench"
            aria-pressed={module === "workbench"}
            onClick={() => {
              if (selectedTopic) void enterWorkbench(selectedTopic);
              else setModule("workbench");
            }}
          >
            TOPIC 工作台
          </button>
        </div>
        {module === "workbench" && (
          <div className="topic-pick" id="topicPickWrap">
            Topic
            <select
              id="topicPick"
              aria-label="切换聚焦 Topic"
              value={selectedTopic}
              onChange={(ev) => void enterWorkbench(ev.target.value)}
            >
              {topics.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.id}
                </option>
              ))}
            </select>
          </div>
        )}
        {module === "workbench" && (
          <div className="planes" role="group" aria-label="平面切换" id="planeSwitch">
            {(
              [
                ["product", "业务平面"],
                ["control", "Control"],
                ["runtime", "Runtime"],
                ["replay", "Replay"],
              ] as Array<[ProjPlane, string]>
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                data-plane={id === "product" ? "business" : id}
                data-ndf-action={`plane-${id}`}
                aria-pressed={plane === id}
                onClick={() => {
                  setPlane(id);
                  setShowProj(true);
                }}
              >
                {label}
              </button>
            ))}
          </div>
        )}
        <div className="grow" />
        <span className="meta-chip baseline">
          <span className="dot" aria-hidden="true" />
          HEAD <code>{shortSha(snapshot?.repoHead)}</code>
        </span>
        <span className="meta-chip">
          <span className="dot" aria-hidden="true" />
          快照 {freshness}
        </span>
        <span className="sot-flag" title="META-011：工作台是树/图/git 的派生投影，不是第五 SoT">
          投影 · 非SoT
        </span>
        <button
          type="button"
          className="btn-ghost btn-acts"
          id="btnActs"
          data-ndf-action="btn-acts"
          onClick={() => setShowActs((v) => !v)}
        >
          ☰ 动作
        </button>
        <button
          type="button"
          className="btn-ghost btn-proj"
          id="btnProj"
          data-ndf-action="btn-proj"
          onClick={() => setShowProj((v) => !v)}
        >
          ◧ 投影
        </button>
        <ActionButton
          actionId="refresh-snapshot"
          enabled={enabledOf(snapshot, "refresh-snapshot")}
          onClick={() => void refresh()}
        />
      </header>

      {error && <div className="banner">{error}</div>}

      {module === "overview" && (
        <section className="overview" id="overviewView">
          <div className="ov-scroll">
            <div className="ov-hero">
              <div>
                <div className="eyebrow">Product · 全局把控</div>
                <h1>
                  {snapshot?.business?.identity?.name || "hnsw-predictor"}{" "}
                  <span className="ov-sub">
                    {snapshot?.business?.identity?.goal || "DiskHNSW · NDF 双轨工作流"}
                  </span>
                </h1>
                <p className="lede">
                  探索轨上的每个 POC 都由一次产品意图蒸馏而来：意图 → 产品提案（spec/open/）→ 人工评审 →
                  冻结契约 → TOPIC。本页是全局唯一的意图入口与双轨总览；单个 TOPIC 的执行请进入工作台。
                </p>
              </div>
              <div className="ov-chips">
                <span className="meta-chip">
                  <span className="dot" />
                  金标 <code>{snapshot?.business?.performance?.baselineId || "—"}</code>
                </span>
                <span className="meta-chip">
                  <span className="dot" />
                  提案 {(snapshot?.business?.proposals || []).length} · TOPIC {topics.length}
                </span>
              </div>
            </div>

            <div className="kpi-row" id="kpiRow">
              <div className="kpi">
                <div className="k">探索中 TOPIC</div>
                <div className="v">{exploringTopics.length}</div>
                <div className="n">exploring / closing</div>
              </div>
              <div className="kpi">
                <div className="k">产品提案</div>
                <div className="v">{(snapshot?.business?.proposals || []).length}</div>
                <div className="n">spec/open/</div>
              </div>
              <div className="kpi">
                <div className="k">金标 QPS</div>
                <div className="v">
                  {(snapshot?.business?.performance?.aggQps || [])[0]?.toFixed?.(0) ||
                    snapshot?.business?.performance?.goldenHeadStatus ||
                    "—"}
                </div>
                <div className="n">{shortSha(snapshot?.business?.performance?.goldenSha)}</div>
              </div>
              <div className="kpi">
                <div className="k">Control 阻断</div>
                <div className="v">
                  {(snapshot?.control?.metaGraph?.findings || []).filter((f) => f.severity === "error")
                    .length}
                </div>
                <div className="n">{snapshot?.control?.maturity || "—"}</div>
              </div>
            </div>

            <div className="ov-card intent-card">
              <div className="eyebrow">意图入口 · 全局唯一</div>
              <h2>新产品意图 → 产品提案</h2>
              <p className="sub">
                生成的是 <code>spec/open/</code> 产品提案工单（track=poc|promote|…），不是 process proposal，也不归入
                NDF Control。工作台内禁止自由意图输入。
              </p>
              <textarea
                id="productIntent"
                className={intentWarn ? "warn-empty" : undefined}
                value={productIntent}
                placeholder="描述产品意图，例如：验证热点路径预测缓存对 QPS 与 recall 的影响…"
                onChange={(ev) => {
                  setProductIntent(ev.target.value);
                  if (intentWarn) setIntentWarn(false);
                }}
              />
              <div className="row">
                <button
                  type="button"
                  className="btn"
                  id="btnPreviewProposal"
                  data-ndf-action="copy-prompt"
                  onClick={() => genProposal()}
                >
                  预览产品提案工单
                </button>
                <button
                  type="button"
                  className="btn primary"
                  id="btnGenProposal"
                  data-ndf-action="new-proposal"
                  onClick={() => {
                    genProposal();
                    if (productIntent.trim()) void run("new-proposal", { intent: productIntent.trim() });
                  }}
                >
                  生成并组 pack
                </button>
                <span className="hint2">空意图拒绝 · 四色提示词（含黄意图）仅出现在 Overview</span>
              </div>
              <div className="freeze-flow">
                <span className="ff hi">意图</span>
                <span className="arr">→</span>
                <span className="ff">产品提案</span>
                <span className="arr">→</span>
                <span className="ff">已确认 / 已审核</span>
                <span className="arr">→</span>
                <span className="ff">冻结契约</span>
                <span className="arr">→</span>
                <span className="ff">TOPIC 工作台</span>
              </div>
              {proposalPrompt && (
                <div id="proposalComposer">
                  <div className="legend">
                    <i>
                      <span className="sw" style={{ background: "var(--warn)" }} /> 用户意图
                    </i>
                    <i>
                      <span className="sw" style={{ background: "var(--accent)" }} /> 条款铆钉
                    </i>
                    <i>
                      <span className="sw" style={{ background: "var(--ctx)" }} /> git/快照
                    </i>
                  </div>
                  <pre id="proposalView" className="prompt-view">
                    {colorizePrompt(proposalPrompt, "overview")}
                  </pre>
                  <div className="row" style={{ marginTop: 12 }}>
                    <button
                      type="button"
                      className="btn"
                      id="btnCopyProposal"
                      data-ndf-action="copy-prompt"
                      onClick={() => void copyText(proposalPrompt)}
                    >
                      复制提案提示词
                    </button>
                  </div>
                </div>
              )}
            </div>

            <div className="ov-tracks">
              <div className="ov-card" id="exploreTrack">
                <h2>
                  探索轨 <span className="tag">poc/</span>
                </h2>
                <p className="sub">exploring / closing TOPIC · 进入工作台做机械执行</p>
                {exploringTopics.length === 0 && <p className="sub">当前无 exploring TOPIC</p>}
                {exploringTopics.map((row) => {
                  const isFocused = focused?.id === row.id;
                  const phases = exploreTrackPhases(isFocused ? focused : null, row.baseline);
                  const gaps = isFocused
                    ? readiness.checks.filter((c) => !c.ok).length
                    : row.blockers?.length || 0;
                  const safe = isFocused ? readiness.safe : gaps === 0;
                  return (
                    <div className={`topic-row${safe ? " safe" : ""}`} key={row.id}>
                      <div className="tr-main">
                        <div className="tr-head">
                          <span className="tr-name">{row.id}</span>
                          <span className="tr-title">{row.hypothesis || row.lifecycle}</span>
                          {safe ? (
                            <span className="badge-safe">safe_to_dispatch</span>
                          ) : (
                            <span className="badge-bad">{gaps || "?"} 缺口</span>
                          )}
                        </div>
                        <div className="tr-meta">
                          baseline {row.baseline || "—"} · surface {(row.surface || []).join(",") || "—"}
                        </div>
                        <div className="mini-phases">
                          {phases.map((p) => (
                            <span className="mp" data-st={p.st} key={p.id}>
                              {p.id}
                            </span>
                          ))}
                        </div>
                        {isFocused && (
                          <div className="tr-faces">
                            {readiness.faces.map((f) => (
                              <span
                                className={`tr-face ${f.present ? "present" : "missing"}`}
                                key={f.id}
                              >
                                <span className="fd" />
                                {f.label.replace(".md", "")}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                      <button
                        type="button"
                        className="btn btn-enter"
                        data-topic={row.id}
                        data-ndf-action="enter-workbench"
                        onClick={() => void enterWorkbench(row.id)}
                      >
                        进入工作台
                      </button>
                    </div>
                  );
                })}
              </div>

              <div className="ov-card">
                <h2>
                  晋升轨 / 路线图 <span className="tag">Trunk</span>
                </h2>
                <p className="sub">路线图条目（真实 snapshot）· 晋升动作在工作台 promote 阶段</p>
                {promoteRows.map((row) => (
                  <div className="trunk-row" key={row[0]}>
                    <span className="tt">{row[0]}</span>
                    <span className="td2">{row[3]}</span>
                    <span className="tm">
                      {row[1]} · {row[2]} · <b>{row[4]}</b>
                    </span>
                  </div>
                ))}
                {(snapshot?.business?.proposals || []).slice(0, 3).map((p) => (
                  <div className="trunk-row" key={p[0]}>
                    <span className="tt">{p[0].slice(0, 48)}</span>
                    <span className="td2">{p[1]}</span>
                    <span className="tm">
                      status <b>{p[2]}</b>
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {snapshot?.business?.performance && (
              <div className="ov-card">
                <h2>金标性能投影</h2>
                <GoldenPerformance
                  scenes={snapshot.business.performance.scenes || []}
                  qps={snapshot.business.performance.aggQps || []}
                  recall={snapshot.business.performance.recall || []}
                />
              </div>
            )}
          </div>
        </section>
      )}

      {module === "workbench" && (
        <>
          <div className="phasebar" id="phasebar">
            <div className="topic-id">
              <span className="k">TOPIC</span>
              <span className="v">{focused?.id || selectedTopic || "—"}</span>
              <span className="l">{focused?.lifecycle || "unfocused"}</span>
            </div>
            <div className="stepper" role="tablist" aria-label="五阶段">
              {PHASES.map((p, idx) => (
                <div key={p.id} style={{ display: "contents" }}>
                  {idx > 0 && <span className="ph-arrow">→</span>}
                  <button
                    type="button"
                    className="ph-node"
                    data-phase={p.id}
                    data-state={phaseStates[p.id]}
                    data-ndf-action={`phase-${p.id}`}
                    aria-current={phase === p.id}
                    onClick={() => setPhase(p.id)}
                  >
                    <span className="pn">
                      {p.label}
                      <span className="ph-state">{phaseStates[p.id]}</span>
                    </span>
                    <span className="ps">{p.short}</span>
                    <span className="pd">{p.desc}</span>
                  </button>
                </div>
              ))}
            </div>
          </div>

          <div className="layout" id="workbenchView">
            <aside className="pane pane-actions" aria-label="阶段动作">
              <div className="pane-head">
                动作
                <span className="sub" id="actCount">
                  {sidebarActionCount} · 免意图优先
                </span>
              </div>
              {phase === "execute" && (
                <div className="act-group">
                  <h3>
                    主行动 · Dispatch
                    <span className="g-line" />
                  </h3>
                  <ActionCard
                    actionId={HERO_ACTION_ID}
                    enabled={enabledOf(snapshot, HERO_ACTION_ID)}
                    selected={!humanZoneFocus && selectedActionId === HERO_ACTION_ID}
                    busy={busyAction === HERO_ACTION_ID}
                    why={ACTION_WHY[HERO_ACTION_ID]}
                    onSelect={(aid) => {
                      setHumanZoneFocus(false);
                      setSelectedActionId(aid);
                    }}
                  />
                </div>
              )}
              {phase === "promote" && (
                <>
                  <div className="act-group">
                    <h3>
                      Trunk 金标
                      <span className="g-line" />
                    </h3>
                    <ActionCard
                      actionId="align-golden"
                      enabled={enabledOf(snapshot, "align-golden")}
                      selected={!humanZoneFocus && selectedActionId === "align-golden"}
                      busy={busyAction === "align-golden"}
                      why={ACTION_WHY["align-golden"]}
                      onSelect={(aid) => {
                        setHumanZoneFocus(false);
                        setSelectedActionId(aid);
                      }}
                    />
                  </div>
                  <div className="act-group">
                    <h3>
                      主题收口
                      <span className="g-line" />
                    </h3>
                    {focused ? (
                      <CloseDecisionChips
                        focused={focused}
                        busy={busyAction !== null}
                        onSelect={(intent) => void run("generate-next-step", { intent })}
                      />
                    ) : null}
                    <ActionCard
                      actionId="next-close-hop"
                      enabled={enabledOf(snapshot, "next-close-hop")}
                      selected={!humanZoneFocus && selectedActionId === "next-close-hop"}
                      busy={busyAction === "next-close-hop"}
                      why={ACTION_WHY["next-close-hop"]}
                      onSelect={(aid) => {
                        setHumanZoneFocus(false);
                        setSelectedActionId(aid);
                      }}
                    />
                  </div>
                </>
              )}
              {phase !== "execute" && phase !== "promote" && (
                <div className="act-group">
                  <h3>
                    {PHASES.find((p) => p.id === phase)?.label}
                    <span className="g-line" />
                  </h3>
                  {phase === "explore" ? (
                    <p className="act-empty">
                      本阶段无工作台动作。假设 / 提案 / 设计在 Overview 完成；契约修改请回全局意图入口。
                    </p>
                  ) : null}
                  {phase === "gate" && (
                    <HumanPhraseCard
                      selected={humanZoneFocus}
                      phrases={gateChecklist.map((g) => g.phrase || g.id || "").filter(Boolean)}
                      onSelect={() => {
                        setHumanZoneFocus(true);
                        setSelectedActionId("gate-pipeline");
                      }}
                    />
                  )}
                  {phaseSidebarActions.map((id) => (
                    <ActionCard
                      key={id}
                      actionId={id}
                      enabled={enabledOf(snapshot, id)}
                      selected={!humanZoneFocus && selectedActionId === id}
                      busy={busyAction === id}
                      why={ACTION_WHY[id]}
                      onSelect={(aid) => {
                        setHumanZoneFocus(false);
                        setSelectedActionId(aid);
                      }}
                    />
                  ))}
                </div>
              )}
              <div className="act-group">
                <h3>
                  通用 · Any
                  <span className="g-line" />
                </h3>
                {globalSidebarActions.map((id) => (
                  <ActionCard
                    key={id}
                    actionId={id}
                    enabled={enabledOf(snapshot, id)}
                    selected={!humanZoneFocus && selectedActionId === id}
                    busy={busyAction === id}
                    why={ACTION_WHY[id]}
                    onSelect={(aid) => {
                      setHumanZoneFocus(false);
                      setSelectedActionId(aid);
                    }}
                  />
                ))}
              </div>
            </aside>

            <main className="pane pane-compose" aria-label="冻结契约工单">
              <div className="compose-scroll" id="composeScroll">
                {!focused ? (
                  <div className="empty-state">
                    <div className="big">∅</div>
                    <h2>未聚焦 TOPIC</h2>
                    <p>从 Overview 探索轨进入，或用顶栏 Topic 选择器聚焦。</p>
                  </div>
                ) : phase === "explore" ? (
                  <div className="empty-state">
                    <div className="big">⬡</div>
                    <h2>探索阶段 · 已完成态</h2>
                    <p>
                      假设 / 提案 / 设计在 Overview 意图入口完成。工作台探索节点无左侧动作；契约修改请回 Overview
                      发起新提案。
                    </p>
                  </div>
                ) : !selectedActionId && !humanZoneFocus ? (
                  <div className="empty-state">
                    <div className="big">⬡</div>
                    <h2>{PHASES.find((p) => p.id === phase)?.label}阶段</h2>
                    <p>从左侧选择一个工作流动作。工单由「基线 + 条款 + 冻结契约」机械编译。</p>
                  </div>
                ) : phase === "bind" &&
                  phaseStates.bind === "active" &&
                  readiness.faces.some((f) => !f.present) &&
                  selectedActionId === "binder-pipeline" ? (
                  <div className="empty-state">
                    <div className="big">▦</div>
                    <h2>装订阶段 · 有面缺失</h2>
                    <p>选择「启动装订器」或「基线准备」，生成 OpenClaw 装订 Prompt。不在此输入意图。</p>
                  </div>
                ) : (
                  <>
                    <div className="c-head">
                      <h2>
                        {humanZoneFocus ? "人工口令" : selectedAction?.label || "动作"}
                        {selectedActionId === HERO_ACTION_ID && !humanZoneFocus && (
                          <span className="tag tag-cl">主行动</span>
                        )}
                      </h2>
                      <p className="lede">
                        {humanZoneFocus
                          ? "门禁回执只能由人发出；工作台只投影口令与闸状态。"
                          : ACTION_WHY[selectedActionId] || selectedAction?.clauseRefs.join(" ")}
                      </p>
                      {selectedAction && (
                        <div className="owner-strip">
                          <span className="tag">{providerLabel(providerKind(selectedAction))}</span>
                          {selectedAction.skill && (
                            <span className="tag tag-tool">{selectedAction.skill.split("/").pop()}</span>
                          )}
                          {selectedAction.packTask && (
                            <span className="tag tag-cl">{selectedAction.packTask}</span>
                          )}
                        </div>
                      )}
                    </div>

                    {selectedActionId === HERO_ACTION_ID && (
                      <div className={`ready-panel ${readiness.safe ? "safe" : "unsafe"}`}>
                        <div className="rp-head">
                          <span className="rp-badge">
                            {readiness.safe ? "可派发" : "暂不可派发"}
                          </span>
                          <span className="rp-title">AI hop</span>
                          <span className="rp-sub">{hopStatusLine(focused.agentRun)}</span>
                        </div>
                        {focused.agentRun?.completion_blockers_human?.length ? (
                          <ul className="rp-hop-blockers">
                            {focused.agentRun.completion_blockers_human.map((line) => (
                              <li key={line}>{line}</li>
                            ))}
                          </ul>
                        ) : null}
                        <div className="rp-checks">
                          {readiness.checks.map((c) => (
                            <div className={`rp-check ${c.ok ? "ok" : "bad"}`} key={c.id}>
                              <span className="ic">{c.ok ? "✓" : "✗"}</span>
                              <div>
                                <div className="lb">{c.label}</div>
                                <div className="dt">{c.detail}</div>
                                {!c.ok && c.fix && (
                                  <button
                                    type="button"
                                    className="fx"
                                    data-jump={c.fix}
                                    data-ndf-action={c.fix}
                                    onClick={() => handleReadyFix(c)}
                                  >
                                    修复 · {c.fix === "prepare-acp-lease" ? "准备 ACP 租约" : c.fix}
                                  </button>
                                )}
                                {!c.ok && !c.fix && c.hint ? (
                                  <p className="fx-hint">{c.hint}</p>
                                ) : null}
                              </div>
                            </div>
                          ))}
                        </div>
                        <div className="rp-faces">
                          {readiness.faces.map((f) => (
                            <span
                              className={`rp-face ${f.present ? "present" : "missing"}`}
                              key={f.id}
                            >
                              <span className="fd" />
                              {f.label}
                            </span>
                          ))}
                        </div>
                        <div className="rp-foot">
                          未知 / stale / 缺 capability / 缺 receipt → 全部 fail closed。按钮点击不是人口令。
                        </div>
                        <div className="rp-aux">
                          <span className="rp-aux-label">辅助（不切换主行动）</span>
                          <button
                            type="button"
                            className="btn ghost btn-sm"
                            data-ndf-action="open-delta"
                            disabled={busyAction !== null}
                            onClick={() => void run("open-delta")}
                          >
                            打开 DELTA
                          </button>
                          <button
                            type="button"
                            className="btn ghost btn-sm"
                            data-ndf-action="diagnose-topic"
                            disabled={busyAction !== null}
                            onClick={() => void run("diagnose-topic")}
                          >
                            主题诊断
                          </button>
                          {hasIsolationFinding ? (
                            <button
                              type="button"
                              className="btn ghost btn-sm"
                              data-ndf-action="poc-isolation-repair"
                              disabled={busyAction !== null}
                              onClick={() => void run("poc-isolation-repair")}
                            >
                              修复隔离
                            </button>
                          ) : null}
                          {["sent", "awaiting_result"].includes(
                            focused.agentRun?.dispatch_state || "",
                          ) ? (
                            <button
                              type="button"
                              className="btn ghost btn-sm"
                              data-ndf-action="dispatch-probe"
                              disabled={busyAction !== null}
                              onClick={() => {
                                const body = [
                                  "# 检查 worker 存活（不派发）",
                                  `topic: ${focused.id}`,
                                  `dispatch_state: ${focused.agentRun?.dispatch_state}`,
                                  "",
                                  "本聊天回「进展如何」。Command Agent 跑：",
                                  "python3 spec/meta/tools/ndf_workflow_status.py dispatch-probe --json",
                                  "",
                                  "MUST NOT 对同一 pack 再 dispatch-send。「派发」/「继续」只确认发出。",
                                ].join("\n");
                                setCopied(false);
                                setComposePrompt(body);
                                setPromptActionId("dispatch-probe");
                                showToast("已组 dispatch-probe Prompt；复制后在本聊天回「进展如何」");
                              }}
                            >
                              检查 worker 存活
                            </button>
                          ) : null}
                        </div>
                      </div>
                    )}

                    {(humanZoneFocus || phase === "gate") && (
                      <div className="human-zone">
                        <h3>人工口令区 · Human only</h3>
                        <p>
                          三闸口令由人在指挥会话发出；不实现未经本仓合同证明的 <code>ndf gate approve</code>{" "}
                          CLI。可先点「启动门禁」生成 OpenClaw 审计 Prompt。
                        </p>
                        {gateChecklist.map((g) => (
                          <div key={g.id}>
                            <pre className="phrase">
                              {focused.id} · {g.phrase}
                            </pre>
                          </div>
                        ))}
                        <div className="row">
                          <ActionButton
                            actionId="gate-pipeline"
                            enabled={enabledOf(snapshot, "gate-pipeline")}
                            onClick={() => void run("gate-pipeline")}
                          />
                          <span>
                            待口令闸：{awaitingGates.map((g) => g.phrase).join(" / ") || "无"}
                          </span>
                        </div>
                        <div className="gates" style={{ marginTop: 12 }}>
                          {gateChecklist.map((g) => {
                            const st =
                              g.state === "valid"
                                ? "approved"
                                : g.state === "invalidated"
                                  ? "invalidated"
                                  : "awaiting";
                            return (
                              <div className="gate" data-st={st} key={g.id}>
                                <span className="g-dot" />
                                <div>
                                  <div className="g-name">{g.phrase}</div>
                                  <div className="g-binds">{g.id}</div>
                                </div>
                                <span className="g-st">{st}</span>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}

                    <div className="wo">
                      <div className="wo-head">
                        <span className="no">1</span>
                        绑定上下文
                        <span className="wh">git / snapshot</span>
                      </div>
                      <div className="wo-body">
                        <div className="b-line">
                          <span className="b-chip">
                            <span className="k">remote</span>
                            <span className="v">{remoteName}</span>
                          </span>
                          <span className="b-chip">
                            <span className="k">branch</span>
                            <span className="v">{remoteBranch || "—"}</span>
                          </span>
                          <span className="b-chip">
                            <span className="k">HEAD</span>
                            <span className="v">{shortSha(snapshot?.repoHead)}</span>
                          </span>
                          <span className="b-chip">
                            <span className="k">payload</span>
                            <span className="v">{shortSha(snapshot?.payloadSha, 12)}</span>
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="wo">
                      <div className="wo-head">
                        <span className="no">2</span>
                        任务契约（已冻结）
                        <span className="wh">TOPIC → DESIGN → INTERFACE</span>
                      </div>
                      <div className="wo-body contract-block">
                        <div className="ct-row">
                          <span className="k">scope</span>
                          <span className="v mono">poc/{focused.id}/</span>
                        </div>
                        <div className="ct-row">
                          <span className="k">hypothesis</span>
                          <span className="v">
                            {focused.topicOverview?.hypothesis || focused.hypothesis || "—"}
                          </span>
                        </div>
                        <div className="ct-row">
                          <span className="k">surface</span>
                          <span className="v mono">
                            {(focused.topicOverview?.explore_surface || focused.surface || []).join(
                              ", ",
                            ) || "—"}
                          </span>
                        </div>
                        <div className="ct-row">
                          <span className="k">next</span>
                          <span className="v">{focused.commandEntry?.nextStepLine || "—"}</span>
                        </div>
                        <div className="prov">
                          <span className="pv-step">
                            <b>提案</b> {(focused.topicOverview?.idea_sources?.proposal_paths || [])[0] || "—"}
                          </span>
                          <span className="arr">→</span>
                          {gateChecklist.map((g) => (
                            <span className="pv-step" key={g.id}>
                              <b>{g.id}</b>{" "}
                              <span className={g.state === "valid" ? "ok" : "wait"}>
                                {g.state === "valid" ? "✓" : "…"} {g.phrase}
                              </span>
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>

                    {phase === "execute" && focused.decision?.decision_required && (
                      <div className="wo">
                        <div className="wo-head">
                          <span className="no">3</span>
                          探索决策芯片（非自由意图）
                          <span className="wh">generate-next-step</span>
                        </div>
                        <div className="wo-body">
                          <div className="b-line decision-chips">
                            {EXECUTE_DECISION_ORDER.filter(
                              (chip) =>
                                (focused.decision?.offered || []).includes(chip) ||
                                focused.decision?.blocked?.[chip],
                            ).map((chip) => {
                              const offered = (focused.decision?.offered || []).includes(chip);
                              const blockLabel =
                                focused.decision?.blocked_labels?.[chip] ||
                                focused.decision?.blocked?.[chip] ||
                                "";
                              return (
                                <button
                                  key={chip}
                                  type="button"
                                  className={`btn decision-chip${offered ? "" : " is-off"}`}
                                  data-ndf-action="decision-prefill"
                                  disabled={!offered}
                                  title={
                                    offered
                                      ? focused.decision?.meanings?.[chip] || chip
                                      : blockLabel || chip
                                  }
                                  onClick={() =>
                                    offered ? void run("generate-next-step", { intent: chip }) : undefined
                                  }
                                >
                                  <span className="decision-chip-label">
                                    {DECISION_LABELS[chip] || chip}
                                  </span>
                                  <span className="decision-chip-id">{chip}</span>
                                  {!offered && blockLabel ? (
                                    <span className="decision-chip-block">{blockLabel}</span>
                                  ) : null}
                                </button>
                              );
                            })}
                          </div>
                          {focused.decision?.baseline_prepared && !focused.decision?.round_started ? (
                            <p className="wo-note ok-note">
                              基线准备（拷贝+R0）已完成；下一步建议选择 implement（首次按设计实现）。
                            </p>
                          ) : null}
                          <p className="wo-note">
                            工作台禁止 textarea 意图；决策芯片直接作为 generate-next-step 的受控 intent。
                          </p>
                        </div>
                      </div>
                    )}

                    <div className="legend">
                      <i>
                        <span className="sw" style={{ background: "var(--accent)" }} /> 条款铆钉
                      </i>
                      <i>
                        <span className="sw" style={{ background: "var(--ctx)" }} /> git/快照
                      </i>
                      <i>
                        <span className="sw" style={{ background: "var(--ok)" }} /> 冻结契约
                      </i>
                    </div>
                    <pre id="promptView" className="prompt-view">
                      {colorizePrompt(
                        workbenchComposeBody(
                          phase,
                          humanZoneFocus ? "human-phrase" : selectedActionId,
                          focused,
                          selectedAction,
                          snapshot,
                        ),
                        "workbench",
                      )}
                    </pre>
                  </>
                )}
              </div>

              <div className="action-bar">
                <button
                  type="button"
                  className="btn primary hero"
                  id="btnCopy"
                  data-ndf-action={humanZoneFocus ? "jump-human-phrase" : selectedActionId}
                  disabled={
                    humanZoneFocus
                      ? false
                      : phase === "explore" ||
                        !selectedActionId ||
                        busyAction !== null ||
                        selectedEnabled?.enabled !== true ||
                        (selectedActionId === HERO_ACTION_ID && !readiness.safe)
                  }
                  onClick={() => void dispatchSelected()}
                >
                  {humanZoneFocus
                    ? "复制人口令说明"
                    : selectedActionId === HERO_ACTION_ID
                      ? "派发探索任务"
                      : selectedAction?.label || "派发"}
                </button>
                <button
                  type="button"
                  className="btn ghost"
                  data-ndf-action="copy-prompt"
                  disabled={!composePrompt && !dialog}
                  onClick={() => void copyText(composePrompt || dialog?.body || "")}
                >
                  {copied
                    ? "已复制"
                    : composePrompt && promptActionId && promptActionId !== selectedActionId
                      ? "复制上次 Prompt"
                      : "复制 Prompt"}
                </button>
                <span className="action-note">
                  {phase === "explore"
                    ? "探索阶段无工作台派发；请回 Overview"
                    : heroEnabled || humanZoneFocus
                      ? "两步派发：本按钮只组 pack / 出 Prompt；validated completion 看磁盘回执"
                      : "fail closed — 先点修复入口"}
                </span>
              </div>
            </main>

            <aside className="pane pane-proj" aria-label="投影">
              <div className="pv-tabs" role="tablist">
                {(
                  [
                    ["product", "三空间"],
                    ["control", "Control"],
                    ["runtime", "Runtime"],
                    ["replay", "Replay"],
                  ] as Array<[ProjPlane, string]>
                ).map(([id, label]) => (
                  <button
                    key={id}
                    type="button"
                    role="tab"
                    aria-selected={plane === id}
                    data-ndf-action={`plane-${id}`}
                    onClick={() => setPlane(id)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div className="pv-body" id="pvBody">
                {plane === "product" && focused && (
                  <>
                    {(["design", "implementation", "test"] as const).map((key) => {
                      const space = focused.spaces?.[key];
                      const ready = space?.ready === true;
                      return (
                        <div className="space" key={key}>
                          <div className="sp-head">
                            <span className="sp-name">{key}</span>
                            <span className={`sp-st ${ready ? "ready" : "gap"}`}>
                              {ready ? "ready" : "gap"}
                            </span>
                            <span className="sp-q">{space?.purpose || ""}</span>
                          </div>
                          {ready ? (
                            <div className="sp-ok">无缺口</div>
                          ) : (
                            (space?.repairs || space?.gaps || []).map((item, idx) => {
                              if (typeof item === "string") {
                                return (
                                  <div className="gap-item" key={item}>
                                    <div className="why">{item}</div>
                                  </div>
                                );
                              }
                              return (
                                <div className="gap-item" key={`${item.kind}-${idx}`}>
                                  <div className="why">{item.why || item.kind}</div>
                                  <div className="how">{item.fix || item.label}</div>
                                  {item.actionId && (
                                    <button
                                      type="button"
                                      className="gap-fix"
                                      data-ndf-action={item.actionId}
                                      onClick={() => jumpTo(item.actionId!, ACTION_PHASE[item.actionId!] === "_all" ? phase : (ACTION_PHASE[item.actionId!] as PhaseId))}
                                    >
                                      修复 · {item.label || item.actionId}
                                    </button>
                                  )}
                                </div>
                              );
                            })
                          )}
                        </div>
                      );
                    })}
                    <div className="h-block">
                      <h4>TOPIC 概览</h4>
                      <TopicOverview
                        topics={topics}
                        focusedId={focused.id}
                        onOpenWorkbench={(id) => void enterWorkbench(id)}
                      />
                    </div>
                  </>
                )}
                {plane === "control" && (
                  <>
                    <div className="h-block">
                      <h4>
                        Genesis
                        <span className="v">
                          {snapshot?.control?.genesis?.project_maturity || "—"}
                        </span>
                      </h4>
                      <p className="pv-note">
                        {snapshot?.control?.genesis?.accepted
                          ? "内核已绑定；日常指挥走 Overview / Workbench。"
                          : "流程内核待安装。"}
                      </p>
                      <ActionButton
                        actionId="new-genesis"
                        enabled={enabledOf(snapshot, "new-genesis")}
                        onClick={() => void run("new-genesis")}
                      />
                    </div>
                    <div className="h-block">
                      <h4>
                        Meta checks
                        <span className="v">
                          {Object.keys(snapshot?.control?.metaGraph?.checks || {}).length}
                        </span>
                      </h4>
                      {Object.entries(snapshot?.control?.metaGraph?.checks || {}).map(([name, st]) => (
                        <div className="h-row" key={name}>
                          {name}
                          <b className={st.state === "passed" ? "" : "hl"}>{st.state}</b>
                        </div>
                      ))}
                      <div className="b-line" style={{ marginTop: 8 }}>
                        <ActionButton
                          actionId="run-ndf-control-check"
                          enabled={enabledOf(snapshot, "run-ndf-control-check")}
                          onClick={() => void run("run-ndf-control-check")}
                        />
                        <ActionButton
                          actionId="diagnose-advisor"
                          enabled={enabledOf(snapshot, "diagnose-advisor")}
                          onClick={() => void run("diagnose-advisor")}
                        />
                      </div>
                    </div>
                  </>
                )}
                {plane === "runtime" && (
                  <>
                    {agentCards.map((agent) => (
                      <div
                        className="agent"
                        data-run={
                          agent.status.includes("running")
                            ? "running"
                            : agent.status.includes("unavail") || agent.status === "offline"
                              ? "offline"
                              : "idle"
                        }
                        key={agent.id}
                      >
                        <div className="ag-head">
                          <span className="ag-dot" />
                          <span className="ag-name">{agent.name}</span>
                          <span className="ag-role">{agent.role}</span>
                        </div>
                        <div className="ag-detail">
                          {agent.provider} · {agent.status}
                          <br />
                          {agent.session}
                          <br />
                          {agent.workspace}
                        </div>
                        <div className="ag-3layer">
                          <b>边界</b> {agent.boundaries}
                          <br />
                          {agent.note}
                        </div>
                      </div>
                    ))}
                    <ActionButton
                      actionId="refresh-snapshot"
                      enabled={enabledOf(snapshot, "refresh-snapshot")}
                      onClick={() => void run("refresh-snapshot", { probeMode: "light" })}
                    />
                  </>
                )}
                {plane === "replay" && (
                  <>
                    <p className="pv-note">
                      回放是投影；{hops.length} episodes
                      {snapshot?.replay?.omittedCount
                        ? ` · omitted ${snapshot.replay.omittedCount}`
                        : ""}
                    </p>
                    {hops.slice(0, 12).map((ep) => (
                      <div
                        className="ep"
                        data-plane={ep.plane}
                        data-status={ep.replayStatus}
                        key={ep.id}
                        onClick={() => {
                          setSelectedHop(ep.id);
                          void run("inspect-ledger", { episode: ep.id });
                        }}
                      >
                        <div className="ep-head">
                          <span className="ep-dot" />
                          <span className="ep-title">{ep.title || ep.label || ep.id}</span>
                          <span className="ep-lv">{ep.lenses?.[0] || ep.agent || ""}</span>
                        </div>
                        <div className="ep-meta">
                          <span>{ep.task}</span>
                          <span>{ep.happenedAt}</span>
                        </div>
                        {selectedHop === ep.id && (
                          <div className="ep-detail">
                            {ep.resultLine || ep.prompt?.slice(0, 160) || "—"}
                            <div className="b-line" style={{ marginTop: 8 }}>
                              <ActionButton
                                actionId="command-replay-run"
                                enabled={enabledOf(snapshot, "command-replay-run")}
                                onClick={() => void run("command-replay-run", { episode: ep.id })}
                              />
                              <ActionButton
                                actionId="command-replay-compare"
                                enabled={enabledOf(snapshot, "command-replay-compare")}
                                onClick={() => void run("command-replay-compare", { episode: ep.id })}
                              />
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </>
                )}
              </div>
            </aside>
          </div>
        </>
      )}

      <footer className="statusbar">
        <span>
          {remoteName}/{remoteBranch || "—"} @ {shortSha(snapshot?.repoHead)}
        </span>
        <span className="grow" />
        {!readiness.safe && module === "workbench" && (
          <span className="gate-warn">fail closed · 见就绪面板修复入口</span>
        )}
        <span>payload {shortSha(snapshot?.payloadSha, 10)}</span>
      </footer>

      {toast && <div className={`toast show`}>{toast}</div>}

      {dialog && (
        <div
          className="modal open"
          role="dialog"
          aria-modal="true"
          aria-label={dialog.title}
          onClick={(ev) => {
            if (ev.target === ev.currentTarget) setDialog(null);
          }}
        >
          <div className="modal-card" ref={dialogRef}>
            <button
              type="button"
              className="modal-close"
              data-ndf-action="collapse-section"
              onClick={() => setDialog(null)}
            >
              关闭
            </button>
            <h2>{dialog.title}</h2>
            {dialog.hint && <p className="pv-note">{dialog.hint}</p>}
            <pre className="prompt-view" style={{ maxHeight: "50vh", overflow: "auto" }}>
              {colorizePrompt(dialog.body, module === "overview" ? "overview" : "workbench")}
            </pre>
            <div className="row" style={{ marginTop: 12, display: "flex", gap: 8 }}>
              <button
                type="button"
                className="btn primary"
                data-ndf-action="copy-prompt"
                onClick={() => void copyText(dialog.body)}
              >
                {copied ? "已复制" : "复制"}
              </button>
              <button
                type="button"
                className="btn ghost"
                data-ndf-action="collapse-section"
                onClick={() => setDialog(null)}
              >
                Dismiss
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function buildAgentCards(
  snapshot: Snapshot | null,
  focused: FocusedTopic | null | undefined,
  freshness: string,
): Array<{
  id: ReplayAgentLens;
  name: string;
  role: string;
  provider: string;
  status: string;
  session: string;
  workspace: string;
  boundaries: string;
  note: string;
}> {
  return [
    {
      id: "command-agent",
      name: "Command Agent",
      role: "Human-facing Composer orchestration",
      provider: "Cursor Commander",
      status: freshness,
      session: snapshot?.absorbedActionId || "no absorbed action",
      workspace: `HEAD ${shortSha(snapshot?.repoHead)}`,
      boundaries: "Prompt / pack only；目标分支不另建 — worker 可用隔离 worktree",
      note: String(snapshot?.projectionFreshness?.latest_action?.operation || "—"),
    },
    {
      id: "openclaw",
      name: "OpenClaw",
      role: "Control: gate / binder / 产品提案编排",
      provider: snapshot?.runtime?.control?.provider || "openclaw",
      status:
        snapshot?.runtime?.control?.reachable === true
          ? snapshot?.runtime?.control?.sessionDispatchable === false
            ? "session_invalid"
            : "reachable"
          : snapshot?.runtime?.control?.reachable === false
            ? "unavailable"
            : "not_probed",
      session: snapshot?.runtime?.control?.defaultSessionKey || "—",
      workspace: `${snapshot?.runtime?.control?.workspace?.state || "unknown"}`,
      boundaries: "不写 src/；不代写人口令；不做 Golden 重跑",
      note: snapshot?.runtime?.control?.sessionFixHint || snapshot?.runtime?.control?.probeError || "—",
    },
    {
      id: "claude-code",
      name: "Claude Code",
      role: "Implementation/Test: POC · 测量 · DELTA",
      provider: snapshot?.runtime?.implementation?.provider || "claude-code-acp",
      status:
        snapshot?.runtime?.implementation?.status === "reachable" &&
        !focused?.agentRun?.worktree
          ? "reachable_no_lease"
          : snapshot?.runtime?.implementation?.status || "not_probed",
      session: focused?.agentRun?.session_id || snapshot?.runtime?.implementation?.defaultSession || "—",
      workspace: focused?.agentRun?.worktree || snapshot?.runtime?.implementation?.workspace?.state || "—",
      boundaries: "MUST 独立 worktree/branch；禁止改 Trunk 于 poc track",
      note: focused?.agentRun?.worktree
        ? `lease ${focused?.agentRun?.status || "idle"}`
        : snapshot?.runtime?.implementation?.status === "reachable"
          ? "ACP 可达但无隔离租约"
          : `lease ${focused?.agentRun?.status || "idle"}`,
    },
    {
      id: "context-compiler",
      name: "Context Compiler",
      role: "ndf_context manifest / role-plan",
      provider: "local tools",
      status: focused?.delegation?.context_verify?.valid ? "valid" : "check",
      session: focused?.delegation?.context_plan?.plan_sha?.slice(0, 12) || "—",
      workspace: "mechanical context",
      boundaries: "只读装订；不派工",
      note: `${focused?.delegation?.context_plan?.read_count ?? "—"} reads`,
    },
  ];
}

createRoot(document.getElementById("root")!).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>,
);
