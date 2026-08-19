import {
  Component,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ErrorInfo,
  type ReactElement,
  type ReactNode,
  type UIEvent,
} from "react";
import { createRoot } from "react-dom/client";
import { ActionButton } from "./ActionButton";
import { dispatchAction, loadSnapshot } from "./api";
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

function VirtualRows<T>({ items, render }: { items: T[]; render: (item: T, index: number) => ReactElement }) {
  const [start, setStart] = useState(0);
  const row = 28;
  const visible = 8;
  const onScroll = (event: UIEvent<HTMLDivElement>) => {
    setStart(Math.floor(event.currentTarget.scrollTop / row));
  };
  const slice = items.slice(start, start + visible + 2);
  return (
    <div className="virtual" onScroll={onScroll}>
      <div style={{ height: items.length * row, position: "relative" }}>
        <div style={{ position: "absolute", top: start * row, left: 0, right: 0 }}>
          {slice.map((item, index) => render(item, start + index))}
        </div>
      </div>
    </div>
  );
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
          setDialog({
            title: `${action.label} · Composer (click is not ${action.humanPhrase || "a gate"})`,
            body: result.prompt,
          });
        } else if (result.path) {
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
          <section className="card">
            <h2>Product</h2>
            <p className="muted">Golden {snapshot?.business?.performance?.goldenHeadStatus} · {snapshot?.business?.performance?.baselineId}</p>
            {snapshot?.business?.performance?.warning && <p className="danger">{snapshot.business.performance.warning}</p>}
            <div className="pills">
              <ActionButton actionId="open-charter" enabled={enabledOf(snapshot, "open-charter")} onClick={() => run("open-charter")} />
              <ActionButton actionId="open-golden" enabled={enabledOf(snapshot, "open-golden")} onClick={() => run("open-golden")} />
              <ActionButton actionId="align-golden" enabled={enabledOf(snapshot, "align-golden")} onClick={() => run("align-golden")} />
            </div>
            <label className="muted">描述要探索或变更的产品想法</label>
            <textarea value={productIntent} onChange={(event) => setProductIntent(event.target.value)} />
            <ActionButton
              actionId="new-proposal"
              enabled={enabledOf(snapshot, "new-proposal")}
              intent={productIntent}
              onClick={() => run("new-proposal", { intent: productIntent })}
            />
            <h3>Active topics</h3>
            <TopicOverview
              topics={topics}
              focusedId={snapshot?.business?.focusedTopicId}
              onOpenWorkbench={(id) => {
                setSelectedTopic(id);
                void run("open-workbench", { topic: id }).then(() => setTab("topics"));
              }}
            />
            <VirtualRows
              items={topics}
              render={(row) => (
                <div key={row.id} className="row">
                  <span>{row.id}</span>
                  <span className="muted">{row.lifecycle}</span>
                  {row.id !== snapshot?.business?.focusedTopicId && (
                    <ActionButton
                      actionId="open-workbench"
                      enabled={enabledOf(snapshot, "open-workbench")}
                      onClick={() => void run("open-workbench", { topic: row.id }).then(() => setTab("topics"))}
                    />
                  )}
                </div>
              )}
            />
          </section>
        )}

        {tab === "topics" && (
          <section className="card">
            <h2>Topics</h2>
            <select
              value={selectedTopic}
              onChange={(event) => setSelectedTopic(event.target.value)}
            >
              {topics.map((row) => (
                <option key={row.id} value={row.id}>{row.id}</option>
              ))}
            </select>
            {selectedTopic && selectedTopic !== snapshot?.business?.focusedTopicId && (
              <ActionButton
                actionId="open-workbench"
                enabled={enabledOf(snapshot, "open-workbench")}
                onClick={() => run("open-workbench", { topic: selectedTopic })}
              />
            )}
            {focused && selectedTopic === snapshot?.business?.focusedTopicId && (
              <>
                <div className="card">
                  <h3>TOPIC 总览</h3>
                  <p>{String(focused.topicOverview?.purpose || focused.hypothesis || "")}</p>
                  <ActionButton actionId="open-topic" enabled={enabledOf(snapshot, "open-topic")} onClick={() => run("open-topic")} />
                </div>
                <div className="grid-3">
                  <div className="card">
                    <h3>Design</h3>
                    <p className="muted">{focused.spaces?.design?.purpose}</p>
                    <ActionButton actionId="gate-pipeline" enabled={enabledOf(snapshot, "gate-pipeline")} onClick={() => run("gate-pipeline")} />
                    <ActionButton actionId="binder-pipeline" enabled={enabledOf(snapshot, "binder-pipeline")} onClick={() => run("binder-pipeline")} />
                    <ActionButton actionId="binder-amend" enabled={enabledOf(snapshot, "binder-amend")} onClick={() => run("binder-amend")} />
                  </div>
                  <div className="card">
                    <h3>Implementation</h3>
                    <p className="muted">本轮决策在页底</p>
                    <ActionButton actionId="poc-prepare-baseline" enabled={enabledOf(snapshot, "poc-prepare-baseline")} onClick={() => run("poc-prepare-baseline")} />
                    <ActionButton actionId="poc-isolation-repair" enabled={enabledOf(snapshot, "poc-isolation-repair")} onClick={() => run("poc-isolation-repair")} />
                  </div>
                  <div className="card">
                    <h3>Test</h3>
                    <ActionButton actionId="open-delta" enabled={enabledOf(snapshot, "open-delta")} onClick={() => run("open-delta")} />
                    <ActionButton actionId="poc-measurement" enabled={enabledOf(snapshot, "poc-measurement")} onClick={() => run("poc-measurement")} />
                  </div>
                </div>
                <div className="card">
                  <h3>阻塞与修复</h3>
                  <ActionButton actionId="refresh-topic" enabled={enabledOf(snapshot, "refresh-topic")} onClick={() => run("refresh-topic", { topic: focused.id })} />
                  <ActionButton actionId="diagnose-topic" enabled={enabledOf(snapshot, "diagnose-topic")} onClick={() => run("diagnose-topic")} />
                  <table>
                    <thead><tr><th>Kind</th><th>Space</th><th>Why</th></tr></thead>
                    <tbody>
                      {(focused.health?.findings || []).map((item, index) => (
                        <tr key={index}><td>{item.kind}</td><td>{item.space}</td><td>{item.why_blocked}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <button type="button" data-ndf-action="collapse-section" onClick={() => setCollapsed((s) => ({ ...s, foundation: !s.foundation }))}>
                  NDF 基础追溯
                </button>
                {!collapsed.foundation && <pre className="muted">{JSON.stringify(focused, null, 2).slice(0, 800)}</pre>}
                <button type="button" data-ndf-action="collapse-section" onClick={() => setCollapsed((s) => ({ ...s, workflow: !s.workflow }))}>
                  NDF 工作流 / Meta
                </button>
                <button type="button" data-ndf-action="collapse-section" onClick={() => setCollapsed((s) => ({ ...s, mechanical: !s.mechanical }))}>
                  机械上下文
                </button>
                {!collapsed.mechanical && (
                  <p className="muted">
                    {focused.delegation?.context_plan?.role} · plan {focused.delegation?.context_plan?.plan_sha?.slice(0, 12)}
                  </p>
                )}
                <div className="card">
                  <h3>本轮决策与实现委派</h3>
                  <div className="pills">
                    {(focused.decision?.offered || ["implement", "continue_exploring", "amend", "reject"]).map((chip) => (
                      <button
                        key={chip}
                        type="button"
                        data-ndf-action="decision-prefill"
                        onClick={() => setDecisionText(chip)}
                      >
                        {chip}
                      </button>
                    ))}
                  </div>
                  <textarea value={decisionText} onChange={(event) => setDecisionText(event.target.value)} />
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
            <button type="button" data-ndf-action="collapse-section" onClick={() => setDialog(null)}>Dismiss</button>
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
