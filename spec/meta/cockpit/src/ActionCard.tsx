import { requireAction } from "./catalog";
import {
  HERO_ACTION_ID,
  providerKind,
  providerLabel,
  providerTagClass,
  type PhaseId,
} from "./phaseMap";
import type { EnabledAction } from "./types";

function formatDisableReason(actionId: string, reason: string | null | undefined): string {
  if (!reason) return "disabled";
  if (actionId === "poc-prepare-baseline" && reason.includes("gapMissingBaseline")) {
    return "基线工作区已就绪";
  }
  return reason;
}

type Props = {
  actionId: string;
  enabled?: EnabledAction;
  selected?: boolean;
  busy?: boolean;
  /** Display-only why line; falls back to clause refs. */
  why?: string;
  onSelect: (actionId: string) => void;
};

export function ActionCard({
  actionId,
  enabled,
  selected,
  busy,
  why,
  onSelect,
}: Props) {
  const action = requireAction(actionId);
  const snapshotEnabled = enabled?.enabled === true;
  const intentBlocked = action.requiresIntent;
  // Workbench cards never carry free-form intent; requiresIntent actions stay
  // selectable for decision-chip driven runs, but show as needing chip.
  const canRun = snapshotEnabled && !busy && (!intentBlocked || actionId === "generate-next-step");
  if ((enabled?.failClosed ?? action.failClosed) === "hide" && !snapshotEnabled) {
    return null;
  }
  const kind = providerKind(action);
  const blocked = !snapshotEnabled
    ? enabled == null
      ? "missing_enabledActions"
      : formatDisableReason(actionId, enabled.reason)
    : busy
      ? "busy"
      : null;
  const isHero = actionId === HERO_ACTION_ID;
  const classes = [
    "act-card",
    isHero ? "hero-card" : "",
    !snapshotEnabled || blocked ? "is-off" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button
      type="button"
      className={classes}
      data-id={actionId}
      data-ndf-action={actionId}
      data-phase={(action.phase as PhaseId | undefined) || undefined}
      aria-current={selected ? "true" : undefined}
      title={blocked ? `${action.label} · ${blocked}` : action.clauseRefs.join(" ")}
      onClick={() => onSelect(actionId)}
    >
      <div className="a-top">
        <span className="a-name">{action.label}</span>
      </div>
      <span className="a-why">
        {why || action.why || action.clauseRefs.map((c) => `[[${c}]]`).join(" ")}
      </span>
      <div className="a-meta">
        <i className={`tag ${providerTagClass(kind)}`}>{providerLabel(kind)}</i>
        {action.requiresIntent ? <i className="tag tag-block">需决策芯片</i> : <i className="tag">免意图</i>}
        {blocked ? <i className="tag tag-block">{blocked}</i> : null}
        {action.clauseRefs.slice(0, 2).map((ref) => (
          <i className="tag tag-cl" key={ref}>
            {ref}
          </i>
        ))}
      </div>
      {!canRun && !blocked ? null : null}
    </button>
  );
}

/** Human-zone card is a projection of gate-pipeline phrases — not a registry action. */
export function HumanPhraseCard({
  selected,
  phrases,
  onSelect,
}: {
  selected?: boolean;
  phrases: string[];
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      className={`act-card human-card${selected ? "" : ""}`}
      data-id="human-phrase"
      data-ndf-action="jump-human-phrase"
      aria-current={selected ? "true" : undefined}
      onClick={onSelect}
    >
      <div className="a-top">
        <span className="a-name">人工口令</span>
      </div>
      <span className="a-why">Human 专属：门禁回执由人触发；不经 Claude Code / OpenClaw 代写口令</span>
      <div className="a-meta">
        <i className="tag tag-hu">Human</i>
        <i className="tag">投影 gate-pipeline</i>
        {phrases.slice(0, 2).map((p) => (
          <i className="tag tag-cl" key={p}>
            {p}
          </i>
        ))}
      </div>
    </button>
  );
}
