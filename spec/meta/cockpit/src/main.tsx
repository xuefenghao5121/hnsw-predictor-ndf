import {
  Component,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ErrorInfo,
  type ReactNode,
} from "react";
import { createRoot } from "react-dom/client";
import { ActionButton } from "./ActionButton";
import { dispatchAction, loadSnapshot } from "./api";
import { GoldenPerformance } from "./charts/GoldenPerformance";
import { ReplayTimeline } from "./charts/ReplayTimeline";
import { TopicOverview } from "./charts/TopicOverview";
import { requireAction } from "./catalog";
import type { EnabledAction, Snapshot, TabId } from "./types";
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

function previewText(value: unknown, fallback = ""): string {
  const text = typeof value === "string" ? value : fallback;
  return text.split("\n").slice(0, 12).join("\n");
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
    genesis: false,
  });
  const [dialog, setDialog] = useState<{ title: string; body: string } | null>(null);
  const [copied, setCopied] = useState(false);
  const [tech, setTech] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const data = await loadSnapshot();
      setError(null);
      setSnapshot(data);
      if (data.business?.identity?.charterExists === false) {
        setTab("control");
      }
      const focused = data.business?.focusedTopicId;
      if (focused) setSelectedTopic(focused);
      const hop = data.replay?.focused?.id;
      if (hop) setSelectedHop(hop);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const run = useCallback(
    async (id: string, extra?: { intent?: string; topic?: string; episode?: string }) => {
      const action = requireAction(id);
      if (action.dispatch === "projection_only") {
        return;
      }
      try {
        const result = await dispatchAction({ id, ...extra });
        if (result.snapshot) {
          setSnapshot(result.snapshot);
          setError(null);
        }
        if (result.prompt) {
          setCopied(false);
          setDialog({
            title: `${action.label} · Composer (click is not ${action.humanPhrase || "a gate"})`,
            body: result.prompt,
          });
        } else if (result.path) {
          setCopied(false);
          setDialog({ title: action.label, body: `openFile ${result.path}` });
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    },
    [],
  );

  const topics = snapshot?.business?.topics || [];
  const hops = snapshot?.replay?.episodes || [];
  const focused = snapshot?.business?.focusedTopic;
  const freshness = snapshot?.projectionFreshness?.state || "unknown";

  const defaultTab = useMemo<TabId>(() => {
    if (snapshot?.business?.identity?.charterExists === false) return "control";
    return "product";
  }, [snapshot]);

  useEffect(() => {
    if (!snapshot) return;
    setTab((current) => current || defaultTab);
  }, [snapshot, defaultTab]);

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
        </div>
        {freshness !== "fresh" && (
          <div className="banner">Write CTAs are fail-closed until projection freshness is fresh.</div>
        )}
        <div className="pills">
          <ActionButton actionId="refresh-snapshot" enabled={enabledOf(snapshot, "refresh-snapshot")} onClick={() => run("refresh-snapshot")} className="primary" />
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
                  <p>{focused.topicOverview?.purpose !== "Not explicitly recorded" ? focused.topicOverview?.purpose : focused.hypothesis}</p>
                  <div className="metadata-grid">
                    <span><strong>Surface</strong>{focused.topicOverview?.explore_surface?.join(", ") || "—"}</span>
                    <span><strong>Depends on</strong>{focused.topicOverview?.idea_sources?.depends_on_topics?.join(", ") || "—"}</span>
                    <span><strong>Proposal sources</strong>{focused.topicOverview?.idea_sources?.proposal_paths?.length || 0}</span>
                  </div>
                  <ActionButton actionId="open-topic" enabled={enabledOf(snapshot, "open-topic")} onClick={() => run("open-topic")} />
                </div>

                <div>
                  <p className="eyebrow">2 · Three-space reliability</p>
                  <div className="grid-3">
                    {(["design", "implementation", "test"] as const).map((space) => {
                      const value = focused.spaces?.[space];
                      return (
                        <div className="card space-card" key={space}>
                          <div className="section-heading">
                            <h3>{space[0].toUpperCase() + space.slice(1)}</h3>
                            <span className={`status-chip ${value?.ready ? "ready" : "blocked"}`}>{value?.ready ? "ready" : "blocked"}</span>
                          </div>
                          <p className="muted">{value?.purpose}</p>
                          <p><strong>Gaps</strong> {value?.gaps?.join(", ") || "none"}</p>
                          <p className="muted">{value?.clause_refs?.map((item) => item.id).join(" · ")}</p>
                          {space === "design" && (
                            <div className="pills">
                              <ActionButton actionId="gate-pipeline" enabled={enabledOf(snapshot, "gate-pipeline")} onClick={() => run("gate-pipeline")} />
                              <ActionButton actionId="binder-pipeline" enabled={enabledOf(snapshot, "binder-pipeline")} onClick={() => run("binder-pipeline")} />
                              <ActionButton actionId="binder-amend" enabled={enabledOf(snapshot, "binder-amend")} onClick={() => run("binder-amend")} />
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
          <section className="card">
            <h2>NDF Control</h2>
            <div className="card">
              <button type="button" data-ndf-action="collapse-section" onClick={() => setCollapsed((s) => ({ ...s, genesis: !s.genesis }))}>
                Genesis {snapshot?.control?.genesis?.project_maturity}
              </button>
              {!collapsed.genesis && (
                <ActionButton actionId="new-genesis" enabled={enabledOf(snapshot, "new-genesis")} onClick={() => run("new-genesis")} />
              )}
            </div>
            <div className="card">
              <h3>NDF 内核地图</h3>
              <p className="muted">missing {(snapshot?.control?.kernelMap?.missing_seeds || []).join(", ") || "none"}</p>
              <ActionButton actionId="open-language-md" enabled={enabledOf(snapshot, "open-language-md")} onClick={() => run("open-language-md")} />
              <ActionButton actionId="open-process-md" enabled={enabledOf(snapshot, "open-process-md")} onClick={() => run("open-process-md")} />
              <ActionButton actionId="open-meta-readme" enabled={enabledOf(snapshot, "open-meta-readme")} onClick={() => run("open-meta-readme")} />
            </div>
            <div className="card">
              <h3>内核自洽性</h3>
              <ActionButton actionId="run-ndf-control-check" enabled={enabledOf(snapshot, "run-ndf-control-check")} onClick={() => run("run-ndf-control-check")} />
              <ActionButton actionId="diagnose-advisor" enabled={enabledOf(snapshot, "diagnose-advisor")} onClick={() => run("diagnose-advisor")} />
              <ActionButton actionId="repair-kernel" enabled={enabledOf(snapshot, "repair-kernel")} onClick={() => run("repair-kernel")} />
              <ActionButton actionId="go-product" enabled={enabledOf(snapshot, "go-product")} onClick={() => setTab("product")} />
              <ActionButton actionId="go-topics" enabled={enabledOf(snapshot, "go-topics")} onClick={() => setTab("topics")} />
            </div>
            <div className="card">
              <h3>工作流演进</h3>
              <p>{snapshot?.control?.processHop?.title || "无强制演进"} · {snapshot?.control?.processHop?.hop}</p>
              <ActionButton actionId="land-confirm" enabled={enabledOf(snapshot, "land-confirm")} onClick={() => run("land-confirm")} />
              <ActionButton actionId="land-review" enabled={enabledOf(snapshot, "land-review")} onClick={() => run("land-review")} />
              <label className="muted">描述要改进的 META 工作流</label>
              <textarea value={metaIntent} onChange={(event) => setMetaIntent(event.target.value)} />
              <ActionButton
                actionId="submit-process-improvement"
                enabled={enabledOf(snapshot, "submit-process-improvement")}
                intent={metaIntent}
                onClick={() => run("submit-process-improvement", { intent: metaIntent })}
              />
            </div>
          </section>
        )}

        {tab === "agents" && (
          <section className="card">
            <h2>Agents</h2>
            {["OpenClaw", "Claude Code", "Canvas", "context-compiler"].map((name) => (
              <div className="card" key={name}>
                <h3>{name}</h3>
                <p className="muted">{name === "Canvas" ? "only surface allowed to carry raw human speech" : "identity lens"}</p>
                <ActionButton
                  actionId="replay-agent-filter"
                  enabled={enabledOf(snapshot, "replay-agent-filter")}
                  onClick={() => setTab("replay")}
                />
              </div>
            ))}
          </section>
        )}

        {tab === "replay" && (
          <section className="card">
            <h2>Replay ledger</h2>
            <ReplayTimeline
              hops={hops}
              focusedId={snapshot?.replay?.focused?.id}
              onInspect={(id) => {
                setSelectedHop(id);
                void run("inspect-ledger", { episode: id });
              }}
            />
            <select value={selectedHop} onChange={(event) => setSelectedHop(event.target.value)}>
              {hops.map((hop) => (
                <option key={hop.id} value={hop.id}>{hop.title || hop.id}</option>
              ))}
            </select>
            {selectedHop && selectedHop !== snapshot?.replay?.focused?.id && (
              <ActionButton
                actionId="inspect-ledger"
                enabled={enabledOf(snapshot, "inspect-ledger")}
                onClick={() => run("inspect-ledger", { episode: selectedHop })}
              />
            )}
            {snapshot?.replay?.focused && (
              <div className="card">
                <h3>人话</h3>
                <p>{snapshot.replay.focused.humanUtterance || "—"}</p>
                <h3>规范组装 Prompt</h3>
                <pre>{previewText(snapshot.replay.focused.assembledPrompt?.text, snapshot.replay.focused.assembledPrompt?.whyMissing)}</pre>
                <h3>当时实发 Prompt</h3>
                <pre>{previewText(snapshot.replay.focused.dispatchedPrompt?.text, snapshot.replay.focused.dispatchedPrompt?.whyMissing)}</pre>
                <button type="button" data-ndf-action="expand-tech-details" onClick={() => setTech((value) => !value)}>
                  显示技术细节
                </button>
                {tech && <pre className="muted">{JSON.stringify(snapshot.replay.focused, null, 2).slice(0, 1200)}</pre>}
                <ActionButton actionId="guest-replay-hop" enabled={enabledOf(snapshot, "guest-replay-hop")} onClick={() => run("guest-replay-hop")} />
                <ActionButton actionId="guest-replay-prefix" enabled={enabledOf(snapshot, "guest-replay-prefix")} onClick={() => run("guest-replay-prefix")} />
              </div>
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
