import type { FocusedTopic } from "./types";

const DECISION_LABELS: Record<string, string> = {
  promote: "晋升合入",
  partial: "部分晋升",
  reject: "负结果关闭",
};

const PROMOTE_DECISION_ORDER = ["promote", "partial", "reject"] as const;

type Props = {
  focused: FocusedTopic;
  busy: boolean;
  onSelect: (intent: string) => void;
};

export function CloseDecisionChips({ focused, busy, onSelect }: Props) {
  const decision = focused.decision;
  if (!decision?.decision_required) {
    return (
      <p className="sidebar-chip-note">
        三闸有效且无待选收口时，此处无芯片。Trunk 金标与主题收口相互独立。
      </p>
    );
  }

  return (
    <div className="sidebar-decision-chips">
      {PROMOTE_DECISION_ORDER.filter(
        (chip) => (decision.offered || []).includes(chip) || decision.blocked?.[chip],
      ).map((chip) => {
        const offered = (decision.offered || []).includes(chip);
        const blockLabel = decision.blocked_labels?.[chip] || decision.blocked?.[chip] || "";
        return (
          <button
            key={chip}
            type="button"
            className={`btn decision-chip sidebar-chip${offered ? "" : " is-off"}`}
            data-ndf-action="decision-prefill"
            disabled={!offered || busy}
            title={offered ? decision.meanings?.[chip] || chip : blockLabel || chip}
            onClick={() => (offered ? onSelect(chip) : undefined)}
          >
            <span className="decision-chip-label">{DECISION_LABELS[chip] || chip}</span>
            <span className="decision-chip-id">{chip}</span>
            {!offered && blockLabel ? <span className="decision-chip-block">{blockLabel}</span> : null}
          </button>
        );
      })}
      {decision.selected &&
      (decision.selected === "promote" ||
        decision.selected === "partial" ||
        decision.selected === "reject") ? (
        <p className="sidebar-chip-note ok-note">
          已选 {DECISION_LABELS[decision.selected] || decision.selected}；下一步点「继续关闭收口」。
        </p>
      ) : (
        <p className="sidebar-chip-note">芯片写入 TOPIC selected_decision，与 Align Golden 无关。</p>
      )}
    </div>
  );
}
