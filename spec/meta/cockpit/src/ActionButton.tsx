import { requireAction } from "./catalog";
import type { EnabledAction } from "./types";

type Props = {
  actionId: string;
  enabled?: EnabledAction;
  intent?: string;
  title?: string;
  className?: string;
  busy?: boolean;
  onClick: () => void;
};

export function ActionButton({
  actionId,
  enabled,
  intent,
  title,
  className,
  busy,
  onClick,
}: Props) {
  const action = requireAction(actionId);
  // Fail-closed: missing enabledActions entry MUST disable, never default-enable.
  const snapshotEnabled = enabled?.enabled === true;
  const intentOk = !action.requiresIntent || Boolean(intent?.trim());
  const can = snapshotEnabled && intentOk && !busy;
  if ((enabled?.failClosed ?? action.failClosed) === "hide" && !snapshotEnabled) {
    return null;
  }
  const blocked = !can
    ? busy
      ? "busy"
      : enabled == null
        ? "missing_enabledActions"
        : enabled?.reason || (action.requiresIntent && !intentOk ? "needs_intent" : "disabled")
    : null;
  const label = busy
    ? `${action.label}…`
    : blocked
      ? `${action.label} · ${blocked}`
      : action.label;
  return (
    <button
      type="button"
      data-ndf-action={actionId}
      className={className}
      title={blocked ? `${action.label} · ${blocked}` : title || action.clauseRefs.join(" ")}
      disabled={!can}
      onClick={onClick}
    >
      {label}
    </button>
  );
}
