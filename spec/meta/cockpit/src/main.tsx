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
import { dispatchAction, isStandaloneCommander, loadSnapshot, watchLiveSnapshot } from "./api";
import { GoldenPerformance } from "./charts/GoldenPerformance";
import { TopicOverview } from "./charts/TopicOverview";
import { requireAction } from "./catalog";
import type { EnabledAction, ReplayAgentLens, Snapshot, TabId } from "./types";
import "./styles.css";

const TAB_ACTIONS: Record<TabId, string> = {
  product: "tab-product",
  topics: "tab-topics",
  control: "tab-control",
  agents: "tab-agents",
  replay: "tab-replay",
};

function enabledOf(snapshot: Snapshot | null, id: string): EnabledAction | undefined {
  return snapshot?.enabledActions?.[id];
}

function pipelineStateLabel(state?: string): string {
  const labels: Record<string, string> = {
    not_dispatched: "尚未派发",
    preparing: "正在准备",
    requested: "正在准备",
    sent: "已发送",
    acknowledged: "OpenClaw 已接收",
    waiting_human: "等待人口令",
    running: "执行中",
    in_progress: "执行中",
    blocked: "阻塞",
    failed: "阻塞",
    succeeded: "已完成",
  };
  return labels[state || ""] || state || "尚未派发";
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
      return (
        <div className="banner">
          页面加载出错：{this.state.message}
        </div>
      );
    }
    return this.props.children;
  }
}

function App() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabId>("product");
  const [productIntent, setProductIntent] = useState("");
  const [metaIntent, setMetaIntent] = useState("");
  const [decisionText, setDecisionText] = useState("");
  const [selectedTopic, setSelectedTopic] = useState<string>("");
  const [selectedHop, setSelectedHop] = useState<string>("");
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({
    foundation: true,
    workflow: true,
    mechanical: true,
    genesis: true,
    kernelMap: false,
    controlHealth: false,
  });
  const [dialog, setDialog] = useState<{ title: string; body: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [remoteName, setRemoteName] = useState("origin");
  const [remoteUrl, setRemoteUrl] = useState("");
  const [remoteBranch, setRemoteBranch] = useState("");
  const live = !isStandaloneCommander();
  const snapshotRef = useRef<Snapshot | null>(null);
  const gitRef = useRef({ remoteName, remoteUrl, remoteBranch });
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
      setTab("control");
    }
    const focused = data.business?.focusedTopicId;
    if (focused) setSelectedTopic(focused);
    const hop = data.replay?.focused?.id;
    if (hop) setSelectedHop(hop);
  }, []);

  const refresh = useCallback(async (mode: "full" | "live" = "full") => {
    try {
      const data = await loadSnapshot();
      applySnapshot(data, mode);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [applySnapshot]);

  useEffect(() => {
    void refresh("full");
  }, [refresh]);

  useEffect(() => {
    if (!live) {
      return undefined;
    }
    return watchLiveSnapshot((sha) => {
      if (snapshotRef.current?.payloadSha === sha) {
        return;
      }
      void refresh("live");
    });
  }, [live, refresh]);

  const run = useCallback(
    async (
      id: string,
      extra?: { intent?: string; topic?: string; episode?: string; timelineStep?: number },
    ) => {
      const action = requireAction(id);
      if (action.dispatch === "projection_only") {
        return;
      }
      setBusyAction(id);
      try {
        const result = await dispatchAction({
          id,
          remote: remoteName,
          remoteUrl,
          branch: remoteBranch,
          ...extra,
        });
        if (result.snapshot) {
          setSnapshot(result.snapshot);
          setError(null);
        }
        if (result.prompt) {
          setCopied(false);
          setDialog({
            title: `${action.label} · ${remoteName}/${remoteBranch || "unspecified-branch"}`,
            body: result.prompt,
          });
        } else if (result.path) {
          setCopied(false);
          setDialog({ title: action.label, body: `openFile ${result.path}` });
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setBusyAction(null);
      }
    },
    [remoteBranch, remoteName, remoteUrl],
  );

  const topics = snapshot?.business?.topics || [];
  const hops = snapshot?.replay?.episodes || [];
  const focused = snapshot?.business?.focusedTopic;
  const freshness = snapshot?.projectionFreshness?.state || "unknown";
  const focusedAction = snapshot?.replay?.focused;
  const controlChecks = snapshot?.control?.metaGraph?.checks || {};
  const controlFindings = snapshot?.control?.metaGraph?.findings || [];
  const controlBlockers = controlFindings.filter((item) => item.severity === "error").length;
  const controlWarnings = controlFindings.filter((item) => item.severity !== "error").length;
  const controlPassed = Object.values(controlChecks).filter((item) => item.state === "passed").length;
  const agentCards: Array<{
    id: ReplayAgentLens;
    name: string;
    role: string;
    provider: string;
    status: string;
    session: string;
    workspace: string;
    boundaries: string;
    note: string;
  }> = [
    {
      id: "command-agent",
      name: "Command Agent",
      role: "Human-facing Composer orchestration and closed-catalog dispatch",
      provider: "Cursor Commander",
      status: freshness,
      session: snapshot?.absorbedActionId || "no absorbed action",
      workspace: `HEAD ${snapshot?.repoHead || "—"} · payload ${snapshot?.payloadSha?.slice(0, 12) || "—"}`,
      boundaries: "Prompt dispatch only; never writes .openclaw/state.json",
      note: String(snapshot?.projectionFreshness?.latest_action?.operation || "No latest operation"),
    },
    {
      id: "openclaw",
      name: "OpenClaw",
      role: "Control plane: gate, binder, proposals, process evolution",
      provider: snapshot?.runtime?.control?.provider || "openclaw",
      status:
        snapshot?.runtime?.control?.reachable === true
          ? "reachable"
          : snapshot?.runtime?.control?.reachable === false
            ? "unavailable"
            : "not probed",
      session: snapshot?.runtime?.control?.defaultSessionKey || "no configured session",
      workspace: `${snapshot?.runtime?.control?.workspace?.state || "unknown"} · match ${String(snapshot?.runtime?.control?.workspace?.match)}`,
      boundaries: "Writes focused Control roots; gate and binder ownership stay separate",
      note: snapshot?.runtime?.control?.configuredSessionVisible === false ? "Configured session not visible" : "Refresh probes gateway status",
    },
    {
      id: "claude-code",
      name: "Claude Code",
      role: "Implementation/Test: POC code, measurement, Numbers, DELTA",
      provider: snapshot?.runtime?.implementation?.provider || "claude-code-acp",
      status: focused?.agentRun?.status || snapshot?.runtime?.implementation?.status || "unknown",
      session: focused?.agentRun?.session_id || snapshot?.runtime?.implementation?.defaultSession || "no session",
      workspace: focused?.agentRun?.worktree || snapshot?.runtime?.implementation?.workspace?.state || "unbound",
      boundaries: "Writes only delegated POC roots; Trunk requires close integration",
      note: [
        `${snapshot?.runtime?.implementation?.activeRuns?.length || 0} active runs`,
        ...(focused?.delegation?.dispatch_blockers || []),
      ].join(" · "),
    },
    {
      id: "context-compiler",
      name: "context-compiler",
      role: "Manifest, ordered reads, clause seeds, role-plan verification",
      provider: "ndf_context",
      status: focused?.delegation?.context_verify?.valid ? "verified" : "blocked",
      session: focused?.delegation?.context_plan?.plan_sha?.slice(0, 12) || "no plan",
      workspace: focused?.delegation?.context_plan?.role || "no focused role",
      boundaries: "Read/compile only; no product or runtime state writes",
      note: focused?.delegation?.context_verify?.errors?.map((item) => item.kind).join(", ") || "Context plan current",
    },
  ];

  const defaultTab = useMemo<TabId>(() => {
    if (snapshot?.business?.identity?.charterExists === false) return "control";
    return "product";
  }, [snapshot]);

  useEffect(() => {
    if (!snapshot) return;
    setTab((current) => current || defaultTab);
  }, [snapshot, defaultTab]);

  useEffect(() => {
    if (hops.length === 0) {
      setSelectedHop("");
      return;
    }
    setSelectedHop((current) =>
      hops.some((hop) => hop.id === current) ? current : hops[0].id,
    );
  }, [hops]);

  return (
    <>
      <header className="app-header">
        <h1>{snapshot?.business?.identity?.name || "NDF commander"}</h1>
        <p className="muted">{snapshot?.business?.identity?.goal}</p>
        <div className="row muted">
          <span>SHA {snapshot?.repoHead}</span>
          <span>{snapshot?.generatedAt}</span>
          <span>payload {snapshot?.payloadSha?.slice(0, 12)}</span>
          <span className={freshness === "fresh" ? "ok" : "danger"}>{freshness}</span>
          <span className={live ? "ok" : "muted"}>{live ? "自动刷新已开" : "静态页，无自动刷新"}</span>
        </div>
        <div className="git-inputs">
          <label>
            远程仓库
            <input
              value={remoteUrl}
              onChange={(event) => setRemoteUrl(event.target.value)}
              placeholder="https://github.com/org/repo.git"
              spellCheck={false}
            />
          </label>
          <label>
            远程名
            <input
              value={remoteName}
              onChange={(event) => setRemoteName(event.target.value)}
              placeholder="origin"
              spellCheck={false}
            />
          </label>
          <label>
            远程分支
            <input
              value={remoteBranch}
              onChange={(event) => setRemoteBranch(event.target.value)}
              placeholder="cursor/existing-branch"
              spellCheck={false}
            />
          </label>
        </div>
        <p className="muted">
          复制 Prompt 时会把上面的远程仓库和分支作为 `BEGIN NDF GIT INPUT` 输入块写入。
          本地 Agent 必须 checkout 该已有远程分支，不得另建替代 feature branch。
        </p>
        {freshness !== "fresh" && (
          <div className="banner">Write CTAs are fail-closed until projection freshness is fresh.</div>
        )}
        <div className="pills">
          <ActionButton
            actionId="refresh-snapshot"
            enabled={enabledOf(snapshot, "refresh-snapshot")}
            busy={busyAction === "refresh-snapshot"}
            onClick={() => run("refresh-snapshot")}
            className="primary"
          />
        </div>
        <p className="muted">
          Now {snapshot?.business?.nowNextBlocked?.now || "—"} · Next {snapshot?.business?.nowNextBlocked?.next || "—"} · Blocked {snapshot?.business?.nowNextBlocked?.blocked ?? 0}
        </p>
      </header>
      <nav className="tabs">
        {(Object.keys(TAB_ACTIONS) as TabId[]).map((id) => (
          <button
            key={id}
            type="button"
            data-ndf-action={TAB_ACTIONS[id]}
            aria-current={tab === id ? "page" : undefined}
            onClick={() => setTab(id)}
          >
            {requireAction(TAB_ACTIONS[id]).label}
          </button>
        ))}
      </nav>
      {error && (
        <div className="banner">
          页面加载出错：{error}
          <button type="button" data-ndf-action="refresh-snapshot" onClick={() => void refresh()}>
            {requireAction("refresh-snapshot").label}
          </button>
        </div>
      )}
      {!snapshot && !error && <p className="muted">Loading snapshot…</p>}
      <main>
        {tab === "product" && (
          <section className="page-stack">
            <div className="hero card">
              <div>
                <p className="eyebrow">Business Project · {snapshot?.business?.identity?.phase}</p>
                <h2>{snapshot?.business?.identity?.name}</h2>
                <p>{snapshot?.business?.identity?.goal}</p>
              </div>
              <div className="scale-strip">
                {(snapshot?.business?.identity?.scales || []).map(([scale, state]) => (
                  <span className={`status-chip ${state}`} key={scale}>{scale} · {state}</span>
                ))}
              </div>
            </div>

            <div className="card">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">Golden / SLA</p>
                  <h3>{snapshot?.business?.performance?.baselineId}</h3>
                </div>
                <span className={`status-chip ${snapshot?.business?.performance?.goldenHeadStatus}`}>
                  {snapshot?.business?.performance?.goldenHeadStatus}
                </span>
              </div>
              {snapshot?.business?.performance?.warning && <p className="danger">{snapshot.business.performance.warning}</p>}
              <GoldenPerformance
                scenes={snapshot?.business?.performance?.scenes || []}
                qps={snapshot?.business?.performance?.aggQps || []}
                recall={snapshot?.business?.performance?.recall || []}
              />
              <div className="pills">
                <ActionButton actionId="open-charter" enabled={enabledOf(snapshot, "open-charter")} onClick={() => run("open-charter")} />
                <ActionButton actionId="open-golden" enabled={enabledOf(snapshot, "open-golden")} onClick={() => run("open-golden")} />
                <ActionButton actionId="align-golden" enabled={enabledOf(snapshot, "align-golden")} onClick={() => run("align-golden")} />
              </div>
            </div>

            <div className="card command-card">
              <h3>New product proposal</h3>
              <label className="muted">描述要探索或变更的产品想法</label>
              <textarea value={productIntent} onChange={(event) => setProductIntent(event.target.value)} />
              <ActionButton
                actionId="new-proposal"
                enabled={enabledOf(snapshot, "new-proposal")}
                intent={productIntent}
                onClick={() => run("new-proposal", { intent: productIntent })}
              />
            </div>

            <div className="card">
              <h3>Capability portfolio</h3>
              <table>
                <thead><tr><th>Capability</th><th>Stable</th><th>Draft</th><th>Open</th><th>Trunk surface</th></tr></thead>
                <tbody>
                  {(snapshot?.business?.capabilities || []).map(([name, stable, draft, open, path]) => (
                    <tr key={name}><td>{name}</td><td>{stable}</td><td>{draft}</td><td>{open}</td><td className="muted">{path}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="card">
              <h3>Active business topics</h3>
              <TopicOverview
                topics={topics}
                focusedId={snapshot?.business?.focusedTopicId}
                onOpenWorkbench={(id) => {
                  setSelectedTopic(id);
                  void run("open-workbench", { topic: id }).then(() => setTab("topics"));
                }}
              />
              <table>
                <thead><tr><th>Topic</th><th>Lifecycle</th><th>Hypothesis</th><th>Surface</th><th>Baseline</th><th>Blockers</th></tr></thead>
                <tbody>
                  {topics.map((row) => (
                    <tr key={row.id}>
                      <td>{row.id}</td><td>{row.lifecycle}</td><td>{row.hypothesis}</td>
                      <td>{row.surface?.join(", ")}</td><td>{row.baseline}</td><td>{row.blockers?.join(", ") || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="grid-2">
              <div className="card">
                <h3>Product proposals</h3>
                <table>
                  <thead><tr><th>Proposal</th><th>Track</th><th>Status</th></tr></thead>
                  <tbody>
                    {(snapshot?.business?.proposals || []).map(([title, track, status]) => (
                      <tr key={title}><td>{title}</td><td>{track}</td><td>{status}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="card">
                <h3>Roadmap</h3>
                <table>
                  <thead><tr><th>Phase</th><th>Work</th><th>Impact</th><th>Status</th><th>Evidence</th></tr></thead>
                  <tbody>
                    {(snapshot?.business?.roadmap || []).map(([phase, work, impact, status, evidence]) => (
                      <tr key={phase}><td>{phase}</td><td>{work}</td><td>{impact}</td><td>{status}</td><td>{evidence}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="card">
              <h3>Business risks</h3>
              <div className="risk-list">
                {(snapshot?.business?.risks || []).map((risk) => (
                  <div className={`risk ${risk.severity || "info"}`} key={risk.kind}>
                    <strong>{risk.kind}</strong><span>{risk.message}</span>
                  </div>
                ))}
              </div>
            </div>
          </section>
        )}

        {tab === "topics" && (
          <section className="page-stack">
            <div className="card topic-selector">
              <div>
                <p className="eyebrow">Topics directory</p>
                <h2>{selectedTopic || "Select a topic"}</h2>
              </div>
              <select value={selectedTopic} onChange={(event) => setSelectedTopic(event.target.value)}>
                {topics.map((row) => <option key={row.id} value={row.id}>{row.id} · {row.lifecycle}</option>)}
              </select>
              {selectedTopic && selectedTopic !== snapshot?.business?.focusedTopicId && (
                <ActionButton
                  actionId="open-workbench"
                  enabled={enabledOf(snapshot, "open-workbench")}
                  onClick={() => run("open-workbench", { topic: selectedTopic })}
                />
              )}
            </div>
            {focused && selectedTopic === snapshot?.business?.focusedTopicId && (
              <>
                <div className="card">
                  <div className="section-heading">
                    <div><p className="eyebrow">1 · Read only</p><h3>TOPIC 总览</h3></div>
                    <span className={`status-chip ${focused.lifecycle}`}>{focused.lifecycle}</span>
                  </div>
                  <p className="topic-summary">{focused.topicOverview?.summary || focused.topicOverview?.purpose || focused.hypothesis}</p>
                  <ActionButton actionId="open-topic" enabled={enabledOf(snapshot, "open-topic")} onClick={() => run("open-topic")} />
                </div>

                <div>
                  <p className="eyebrow">2 · Three-space reliability</p>
                  <div className="grid-3">
                    {(["design", "implementation", "test"] as const).map((space) => {
                      const value = focused.spaces?.[space];
                      const repairs = value?.repairs || [];
                      return (
                        <div className="card space-card" key={space}>
                          <div className="section-heading">
                            <h3>{space[0].toUpperCase() + space.slice(1)}</h3>
                            <span className={`status-chip ${value?.ready ? "ready" : "blocked"}`}>{value?.ready ? "ready" : "blocked"}</span>
                          </div>
                          <p className="muted">{value?.purpose}</p>
                          {repairs.length === 0 ? (
                            <p><strong>Gaps</strong> none</p>
                          ) : repairs.map((repair) => (
                            <div className="gap-recipe" key={repair.kind}>
                              <p><strong>{repair.kind}</strong></p>
                              <p>{repair.why}</p>
                              <p className="fix-line">{repair.fix}</p>
                              <p className="muted">{repair.owner} · {repair.writeRoot}</p>
                            </div>
                          ))}
                          <p className="muted">{value?.clause_refs?.map((item) => item.id).join(" · ")}</p>
                          {space === "design" && (
                            <div className="pills">
                              <ActionButton actionId="design-prepare" enabled={enabledOf(snapshot, "design-prepare")} onClick={() => run("design-prepare")} />
                            </div>
                          )}
                          {space === "implementation" && (
                            <div className="pills">
                              <ActionButton actionId="poc-prepare-baseline" enabled={enabledOf(snapshot, "poc-prepare-baseline")} onClick={() => run("poc-prepare-baseline")} />
                              <ActionButton actionId="poc-isolation-repair" enabled={enabledOf(snapshot, "poc-isolation-repair")} onClick={() => run("poc-isolation-repair")} />
                            </div>
                          )}
                          {space === "test" && (
                            <div className="pills">
                              <ActionButton actionId="open-delta" enabled={enabledOf(snapshot, "open-delta")} onClick={() => run("open-delta")} />
                              <ActionButton actionId="poc-measurement" enabled={enabledOf(snapshot, "poc-measurement")} onClick={() => run("poc-measurement")} />
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className="card">
                  <div className="section-heading">
                    <div><p className="eyebrow">3 · Evidence routed</p><h3>阻塞与修复</h3></div>
                    <div className="pills">
                      <ActionButton actionId="refresh-topic" enabled={enabledOf(snapshot, "refresh-topic")} onClick={() => run("refresh-topic", { topic: focused.id })} />
                      <ActionButton actionId="diagnose-topic" enabled={enabledOf(snapshot, "diagnose-topic")} onClick={() => run("diagnose-topic")} />
                    </div>
                  </div>
                  <div className="check-strip">
                    {Object.entries(focused.health?.checks || {}).map(([name, check]) => (
                      <span className={`status-chip ${check.state}`} key={name}>{name} · {check.state}</span>
                    ))}
                  </div>
                  <table>
                    <thead><tr><th>Kind</th><th>Space</th><th>NDF 依据</th><th>Why blocked</th><th>Owner / write root</th></tr></thead>
                    <tbody>
                      {(focused.health?.findings || []).map((item, index) => (
                        <tr key={`${item.kind}-${index}`}>
                          <td>{item.kind}</td><td>{item.space}</td>
                          <td>{item.clause_refs?.map((ref) => ref.id).join(", ")}</td>
                          <td>{item.why_blocked}</td>
                          <td>{item.repair_owner} · {item.allowed_write_root}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="card disclosure">
                  <button type="button" data-ndf-action="collapse-section" onClick={() => setCollapsed((s) => ({ ...s, foundation: !s.foundation }))}>
                    4 · NDF 基础追溯 · clauses {focused.ndfFoundation?.clause_count || 0}
                  </button>
                  {!collapsed.foundation && (
                    <div>
                      <p className="muted">Stable summary: {JSON.stringify(focused.ndfFoundation?.stable_summary || {})}</p>
                      <table>
                        <thead><tr><th>Goal / clause</th><th>Design</th><th>Code / commit</th><th>Verification</th></tr></thead>
                        <tbody>
                          {(focused.traceability || []).map((row) => (
                            <tr key={row.goal_or_clause}><td>{row.goal_or_clause}</td><td>{row.design}</td><td>{row.code_or_commit}</td><td>{row.verification}</td></tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>

                <div className="card disclosure">
                  <button type="button" data-ndf-action="collapse-section" onClick={() => setCollapsed((s) => ({ ...s, workflow: !s.workflow }))}>
                    5 · NDF 工作流 / Meta · {focused.workflowMeta?.spec_health_state}
                  </button>
                  {!collapsed.workflow && (
                    <div>
                      <p>{focused.workflowMeta?.note}</p>
                      <div className="check-strip">
                        {Object.entries(focused.workflowMeta?.spec_health_checks || {}).map(([name, state]) => (
                          <span className={`status-chip ${state}`} key={name}>{name} · {state}</span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                <div className="card disclosure">
                  <button type="button" data-ndf-action="collapse-section" onClick={() => setCollapsed((s) => ({ ...s, mechanical: !s.mechanical }))}>
                    6 · 机械上下文 · {focused.delegation?.context_plan?.role || "plan unavailable"}
                  </button>
                  {!collapsed.mechanical && (
                    <div className="metadata-grid">
                      <span><strong>Plan SHA</strong>{focused.delegation?.context_plan?.plan_sha?.slice(0, 12) || "—"}</span>
                      <span><strong>Context verify</strong>{String(focused.delegation?.context_verify?.valid)}</span>
                      <span><strong>Static preflight</strong>{String(focused.delegation?.static_preflight_passed)}</span>
                      <span><strong>Runtime ready</strong>{String(focused.delegation?.runtime_dispatch_ready)}</span>
                      <span><strong>Dispatch blockers</strong>{focused.delegation?.dispatch_blockers?.join(", ") || "none"}</span>
                    </div>
                  )}
                </div>

                <div className="card command-card">
                  <div className="section-heading">
                    <div><p className="eyebrow">7 · Sole full-topic command surface</p><h3>本轮决策与实现委派</h3></div>
                    <span className={`status-chip ${focused.decision?.state}`}>{focused.decision?.state}</span>
                  </div>
                  <div className="command-entry">
                    <strong>命令入口</strong>
                    <span>{focused.commandEntry?.nextStepLine || "Review the current NDF state before dispatch."}</span>
                  </div>
                  <div className="control-pipeline-grid">
                    <div className="pipeline-panel">
                      <div className="section-heading">
                        <div><p className="eyebrow">OpenClaw Control</p><h4>人工门禁 · 3 闸</h4></div>
                        <span className={`status-chip ${focused.controlPipelines?.gate?.dispatch?.state}`}>
                          {pipelineStateLabel(focused.controlPipelines?.gate?.dispatch?.state)}
                        </span>
                      </div>
                      <p className="muted">
                        Gate only writes GATES.md. Click is not TOPIC已审核 / DESIGN已审核 / 可以开始实现.
                      </p>
                      <ol className="pipeline-checklist">
                        {(focused.controlPipelines?.gate?.checklist || []).map((item) => (
                          <li key={item.id}>
                            <strong>{item.phrase}</strong>
                            <span className={`status-chip ${item.state}`}>{item.state || "unknown"}</span>
                          </li>
                        ))}
                      </ol>
                      <p className="muted">
                        {focused.controlPipelines?.gate?.needed
                          ? "有闸缺口：点击生成门禁流水线 Prompt。"
                          : "三闸当前有效。点击仍可复检并生成指挥 Prompt。"}
                      </p>
                      {focused.controlPipelines?.gate?.handoff && (
                        <p className="danger">
                          {focused.controlPipelines.gate.handoff.blocked_gate} blocked by binder · next {focused.controlPipelines.gate.handoff.next_binder_label}
                        </p>
                      )}
                      <ActionButton actionId="gate-pipeline" enabled={enabledOf(snapshot, "gate-pipeline")} onClick={() => run("gate-pipeline")} />
                    </div>
                    <div className="pipeline-panel">
                      <div className="section-heading">
                        <div><p className="eyebrow">OpenClaw Control</p><h4>装订器修订 · 6 面</h4></div>
                        <span className={`status-chip ${focused.controlPipelines?.binder?.dispatch?.state}`}>
                          {pipelineStateLabel(focused.controlPipelines?.binder?.dispatch?.state)}
                        </span>
                      </div>
                      <p className="muted">Binder writes only the focused facet and never approves a gate.</p>
                      <ol className="pipeline-checklist">
                        {(focused.controlPipelines?.binder?.checklist || []).map((item) => (
                          <li key={item.id}>
                            <strong>{item.label}</strong>
                            <span className={`status-chip ${item.exists ? "ready" : "blocked"}`}>
                              {item.exists ? "present" : "missing"}
                            </span>
                          </li>
                        ))}
                      </ol>
                      <p className="muted">
                        {focused.controlPipelines?.binder?.needed
                          ? "有装订器缺口：点击生成装订器流水线 Prompt。"
                          : "六面当前无缺口。点击仍可复检 / 做同假设修订。"}
                      </p>
                      <div className="pills">
                        <ActionButton actionId="binder-pipeline" enabled={enabledOf(snapshot, "binder-pipeline")} onClick={() => run("binder-pipeline")} />
                        <ActionButton actionId="binder-amend" enabled={enabledOf(snapshot, "binder-amend")} onClick={() => run("binder-amend")} />
                      </div>
                    </div>
                  </div>
                  <div className="next-actions">
                    {(focused.health?.next_actions || []).map((action, index) => (
                      <div key={`${action.task}-${index}`}>
                        <strong>{action.label}</strong><span>{action.owner} · {action.space} · {action.allowed_write_root}</span>
                      </div>
                    ))}
                  </div>
                  <p className="muted">
                    Latest {focused.decision?.briefing?.latest_round} · verdict {focused.decision?.briefing?.verdict}
                  </p>
                  <div className="pills">
                    {(focused.decision?.offered || []).map((chip) => (
                      <button key={chip} type="button" data-ndf-action="decision-prefill" onClick={() => setDecisionText(chip)}>{chip}</button>
                    ))}
                  </div>
                  {Object.entries(focused.decision?.blocked || {}).map(([mode, reason]) => (
                    <p className="danger" key={mode}>{mode} blocked: {reason}</p>
                  ))}
                  <textarea value={decisionText} onChange={(event) => setDecisionText(event.target.value)} placeholder="写下本轮决策；空文本不会派发" />
                  <p className="eyebrow">Claude Code implementation</p>
                  <div className="pills">
                    <ActionButton
                      actionId="generate-next-step"
                      enabled={enabledOf(snapshot, "generate-next-step")}
                      intent={decisionText}
                      onClick={() => run("generate-next-step", { intent: decisionText })}
                    />
                    <ActionButton actionId="delegate-poc" enabled={enabledOf(snapshot, "delegate-poc")} onClick={() => run("delegate-poc")} />
                    <ActionButton actionId="prepare-acp-lease" enabled={enabledOf(snapshot, "prepare-acp-lease")} onClick={() => run("prepare-acp-lease")} />
                    <ActionButton actionId="next-close-hop" enabled={enabledOf(snapshot, "next-close-hop")} onClick={() => run("next-close-hop")} />
                  </div>
                  <p className="muted">Click is not 已确认 / TOPIC已审核 / 可以开始实现.</p>
                </div>
              </>
            )}
          </section>
        )}

        {tab === "control" && (
          <section className="page-stack">
            <div className="hero card">
              <div>
                <p className="eyebrow">Meta kernel command plane</p>
                <h2>NDF Control</h2>
                <p>流程内核能否安全指挥 Product、Topics 与 Agent Runtime。</p>
              </div>
              <div className="control-kpis">
                <span><strong>{controlBlockers}</strong>阻断</span>
                <span><strong>{controlWarnings}</strong>告警</span>
                <span><strong>{controlPassed}</strong>通过</span>
              </div>
            </div>

            <div className="card disclosure">
              <button type="button" data-ndf-action="collapse-section" onClick={() => setCollapsed((s) => ({ ...s, genesis: !s.genesis }))}>
                Genesis · {snapshot?.control?.genesis?.project_maturity} · {snapshot?.control?.genesis?.accepted ? "内核已绑定" : "待安装"}
              </button>
              {!collapsed.genesis && (
                <div className="page-stack">
                  <p>
                    {snapshot?.control?.genesis?.accepted
                      ? "内核已绑定；日常指挥走 Product / Topics，不必重跑 Genesis。"
                      : "把流程内核装进本仓；按 G0→G3 完成人工验收。"}
                  </p>
                  <div className="genesis-grid">
                    <span><strong>G0</strong>契约来源</span>
                    <span><strong>G1</strong>双轨边界</span>
                    <span><strong>G2</strong>写入边界</span>
                    <span><strong>G3</strong>验收口径</span>
                  </div>
                  <p className="muted">Binding SHA {snapshot?.control?.genesis?.genesis_trunk_sha || "—"}</p>
                  <ActionButton actionId="new-genesis" enabled={enabledOf(snapshot, "new-genesis")} onClick={() => run("new-genesis")} />
                </div>
              )}
            </div>

            <div className="card disclosure">
              <div className="section-heading">
                <button type="button" data-ndf-action="collapse-section" onClick={() => setCollapsed((s) => ({ ...s, kernelMap: !s.kernelMap }))}>
                  NDF 内核地图 · 种子 {snapshot?.control?.kernelMap?.seeds?.length || 0} · 缺 {(snapshot?.control?.kernelMap?.missing_seeds || []).length}
                </button>
                <div className="pills">
                  <ActionButton actionId="run-ndf-control-check" enabled={enabledOf(snapshot, "run-ndf-control-check")} onClick={() => run("run-ndf-control-check")} />
                  <ActionButton actionId="diagnose-advisor" enabled={enabledOf(snapshot, "diagnose-advisor")} onClick={() => run("diagnose-advisor")} />
                </div>
              </div>
              {!collapsed.kernelMap && (
                <div>
                  <p className="eyebrow">Process profile IR</p>
                  <table>
                    <thead><tr><th>Clause</th><th>Title</th><th>Status</th><th>Role</th><th>Scope</th></tr></thead>
                    <tbody>
                      {(snapshot?.control?.kernelMap?.seeds || []).map((seed) => (
                        <tr key={seed.id}><td>{seed.id}</td><td>{seed.title}</td><td>{seed.status}</td><td>{seed.role}</td><td>{seed.scope}</td></tr>
                      ))}
                    </tbody>
                  </table>
                  {(snapshot?.control?.kernelMap?.missing_seeds || []).length > 0 && (
                    <p className="danger">Missing: {snapshot?.control?.kernelMap?.missing_seeds?.join(", ")}</p>
                  )}
                  <div className="pills">
                    <ActionButton actionId="open-language-md" enabled={enabledOf(snapshot, "open-language-md")} onClick={() => run("open-language-md")} />
                    <ActionButton actionId="open-process-md" enabled={enabledOf(snapshot, "open-process-md")} onClick={() => run("open-process-md")} />
                    <ActionButton actionId="open-meta-readme" enabled={enabledOf(snapshot, "open-meta-readme")} onClick={() => run("open-meta-readme")} />
                  </div>
                </div>
              )}
            </div>

            <div className="card disclosure">
              <div className="section-heading">
                <button type="button" data-ndf-action="collapse-section" onClick={() => setCollapsed((s) => ({ ...s, controlHealth: !s.controlHealth }))}>
                  内核自洽性 · 阻断 {controlBlockers} · 告警 {controlWarnings} · 通过 {controlPassed}
                </button>
                <div className="pills">
                  <ActionButton actionId="run-ndf-control-check" enabled={enabledOf(snapshot, "run-ndf-control-check")} onClick={() => run("run-ndf-control-check")} />
                  <ActionButton actionId="diagnose-advisor" enabled={enabledOf(snapshot, "diagnose-advisor")} onClick={() => run("diagnose-advisor")} />
                </div>
              </div>
              {!collapsed.controlHealth && (
                <div>
                  <p className="eyebrow">Plane-routed checks</p>
                  <table>
                    <thead><tr><th>Check / finding</th><th>State</th><th>Why blocked</th><th>Plane / repair</th></tr></thead>
                    <tbody>
                      {Object.entries(controlChecks).map(([name, check]) => (
                        <tr key={name}><td>{name}</td><td><span className={`status-chip ${check.state}`}>{check.state}</span></td><td>{check.summary}</td><td>inspection</td></tr>
                      ))}
                      {controlFindings.map((finding, index) => (
                        <tr key={`${finding.kind}-${index}`}>
                          <td>{finding.kind}</td><td>{finding.severity}</td><td>{finding.why_blocked}</td>
                          <td>{finding.plane || finding.space || "route by check"} · {finding.repair_task}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div className="pills">
                    <ActionButton actionId="repair-kernel" enabled={enabledOf(snapshot, "repair-kernel")} onClick={() => run("repair-kernel")} />
                    <ActionButton actionId="go-product" enabled={enabledOf(snapshot, "go-product")} onClick={() => setTab("product")} />
                    <ActionButton actionId="go-topics" enabled={enabledOf(snapshot, "go-topics")} onClick={() => setTab("topics")} />
                  </div>
                  {(snapshot?.control?.nextActions || []).length > 0 && (
                    <div className="next-actions">
                      {(snapshot?.control?.nextActions || []).map((action, index) => (
                        <div key={`${action.kind}-${index}`}><strong>{action.label || action.kind}</strong><span>{action.owner} · {action.space} · {action.allowed_write_root}</span></div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="card command-card">
              <div className="section-heading">
                <div><p className="eyebrow">spec/meta only</p><h3>工作流演进</h3></div>
                <span className={`status-chip ${snapshot?.control?.processHop ? "warning" : "passed"}`}>
                  {snapshot?.control?.processHop ? snapshot.control.processHop.hop : "无强制演进"}
                </span>
              </div>
              {snapshot?.control?.processHop && (
                <div className="command-entry">
                  <strong>{snapshot.control.processHop.title}</strong>
                  <span>Next human phrase: {snapshot.control.processHop.nextHumanPhrase}</span>
                </div>
              )}
              <div className="pills">
                <ActionButton actionId="land-confirm" enabled={enabledOf(snapshot, "land-confirm")} onClick={() => run("land-confirm")} />
                <ActionButton actionId="land-review" enabled={enabledOf(snapshot, "land-review")} onClick={() => run("land-review")} />
              </div>
              <table>
                <thead><tr><th>Process proposal</th><th>Hop / status</th><th>Path</th></tr></thead>
                <tbody>
                  {(snapshot?.control?.processProposals || []).map(([title, status, path]) => (
                    <tr key={path}><td>{title}</td><td>{status}</td><td>{path}</td></tr>
                  ))}
                </tbody>
              </table>
              <p className="muted">Archived process proposals: {snapshot?.control?.processProposalArchivedCount || 0}</p>
              <label className="muted">描述要改进的 META 工作流</label>
              <textarea value={metaIntent} onChange={(event) => setMetaIntent(event.target.value)} />
              <ActionButton
                actionId="submit-process-improvement"
                enabled={enabledOf(snapshot, "submit-process-improvement")}
                intent={metaIntent}
                onClick={() => run("submit-process-improvement", { intent: metaIntent })}
              />
            </div>

            <div className="card">
              <h3>执行面卫生</h3>
              <div className="control-kpis">
                <span><strong>{snapshot?.control?.legacyUnknownTopics?.length || 0}</strong>legacy unknown topics</span>
                <span><strong>{snapshot?.control?.invalidatedReceipts?.length || 0}</strong>invalidated receipts</span>
                <span><strong>{snapshot?.control?.proposalPlaneWarnings?.length || 0}</strong>proposal-plane warnings</span>
              </div>
              {(snapshot?.control?.proposalPlaneWarnings || []).map(([path, track, message]) => (
                <div className="risk warning" key={path}><strong>{path}</strong><span>{track} · {message}</span></div>
              ))}
              {(snapshot?.control?.draftMapWarnings || []).map(([clause, path, message]) => (
                <div className="risk info" key={`${clause}-${path}`}><strong>{clause}</strong><span>{path} · {message}</span></div>
              ))}
            </div>
          </section>
        )}

        {tab === "agents" && (
          <section className="page-stack">
            <div className="hero card">
              <div><p className="eyebrow">Agent Runtime</p><h2>Agents</h2><p>身份、会话、工作区绑定与当前阻塞。</p></div>
              <span className="status-chip">Runtime probe only on Refresh snapshot</span>
            </div>
            <div className="agent-grid">
              {agentCards.map((agent) => (
                <div className="card agent-card" key={agent.id}>
                  <div className="section-heading">
                    <div><p className="eyebrow">{agent.provider}</p><h3>{agent.name}</h3></div>
                    <span className={`status-chip ${agent.status}`}>{agent.status}</span>
                  </div>
                  <p>{agent.role}</p>
                  <div className="agent-facts">
                    <span><strong>Session / plan</strong>{agent.session}</span>
                    <span><strong>Workspace</strong>{agent.workspace}</span>
                    <span><strong>Boundary</strong>{agent.boundaries}</span>
                    <span><strong>Current note</strong>{agent.note}</span>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {tab === "replay" && (
          <section className="page-stack">
            <div className="hero card">
              <div>
                <p className="eyebrow">Button action</p>
                <h2>Replay</h2>
                <p>回放前端按钮动作：左列从 git 基线 A 重跑，右列对照主线下一 SHA B。</p>
              </div>
              <span className="status-chip">{hops.length} actions</span>
            </div>
            {hops.length === 0 ? (
              <div className="card">
                <p>尚无带 git A/B 的按钮动作。旧 Canvas 账本已归档，不在此列出。</p>
                {snapshot?.replay?.archivedNote && (
                  <p className="muted">{snapshot.replay.archivedNote}</p>
                )}
              </div>
            ) : (
              <>
                <div className="card">
                  <label>
                    按钮动作
                    <select
                      data-ndf-action="d3-zoom-filter"
                      value={selectedHop}
                      onChange={(event) => {
                        const id = event.target.value;
                        setSelectedHop(id);
                        if (id && id !== snapshot?.replay?.focused?.id) {
                          void run("inspect-ledger", { episode: id });
                        }
                      }}
                    >
                      {hops.map((hop) => (
                        <option key={hop.id} value={hop.id}>
                          {hop.title || hop.label || hop.actionId || hop.id}
                        </option>
                      ))}
                    </select>
                  </label>
                  {focusedAction && selectedHop === focusedAction.id && (
                    <p className="muted">
                      {focusedAction.actionId || focusedAction.label}
                      {" · "}
                      A={(focusedAction.baselineSha || "").slice(0, 12)}
                      {" → "}
                      B={(focusedAction.resultSha || "").slice(0, 12)}
                    </p>
                  )}
                </div>
                {focusedAction && selectedHop === focusedAction.id && (
                  <div className="replay-compare-grid">
                    <div className="card replay-pane">
                      <p className="eyebrow">重跑</p>
                      <h3>执行回放</h3>
                      <p className="muted">从基线 A 开隔离分支，拷贝原按钮 Prompt 重跑（instructions，不宣称已回放）。</p>
                      <ActionButton
                        actionId="command-replay-run"
                        enabled={enabledOf(snapshot, "command-replay-run")}
                        onClick={() => run("command-replay-run", { episode: focusedAction.id })}
                      />
                      <div className="replay-status">
                        <p className="eyebrow">回放后 git 状态</p>
                        {focusedAction.left?.status === "pending" || !focusedAction.left?.head ? (
                          <p>待回放</p>
                        ) : (
                          <pre>
                            {`HEAD ${focusedAction.left.head}\n${focusedAction.left.diffStat || ""}`}
                          </pre>
                        )}
                      </div>
                    </div>
                    <div className="card replay-pane">
                      <p className="eyebrow">原结果</p>
                      <h3>主线对照</h3>
                      <p className="muted">对照主线 A 的下一 SHA B（不重跑 skill）。</p>
                      <ActionButton
                        actionId="command-replay-compare"
                        enabled={enabledOf(snapshot, "command-replay-compare")}
                        onClick={() => run("command-replay-compare", { episode: focusedAction.id })}
                      />
                      <div className="replay-status">
                        <p className="eyebrow">B 的 git 状态</p>
                        <pre>
                          {(focusedAction.right?.showStat || focusedAction.originalShowStat || "")
                            + (focusedAction.right?.diffStat || focusedAction.originalDiffStat
                              ? `\n\n${focusedAction.right?.diffStat || focusedAction.originalDiffStat}`
                              : "")
                            || "—"}
                        </pre>
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}
          </section>
        )}
      </main>
      {dialog && (
        <div className="modal" role="dialog">
          <div className="card">
            <h3>{dialog.title}</h3>
            <pre>{dialog.body}</pre>
            <div className="pills">
              <button
                type="button"
                data-ndf-action="copy-prompt"
                onClick={() => {
                  void navigator.clipboard.writeText(dialog.body).then(() => setCopied(true));
                }}
              >
                {copied ? "已复制" : "复制 Prompt"}
              </button>
              <button type="button" data-ndf-action="collapse-section" onClick={() => setDialog(null)}>Dismiss</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

const root = document.getElementById("root");
if (!root) {
  throw new Error("NDF commander #root missing");
}
createRoot(root).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>,
);
