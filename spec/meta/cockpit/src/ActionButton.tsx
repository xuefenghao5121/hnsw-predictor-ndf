import { requireAction } from "./catalog";
import type { EnabledAction } from "./types";

type Props = {
  actionId: string;
  enabled?: EnabledAction;
  intent?: string;
  title?: string;
  className?: string;
  onClick: () => void;
};

export function ActionButton({ actionId, enabled, intent, title, className, onClick }: Props) {
  const action = requireAction(actionId);
  const snapshotEnabled = enabled?.enabled ?? true;
  const intentOk = !action.requiresIntent || Boolean(intent?.trim());
  const can = snapshotEnabled && intentOk;
  if (enabled?.failClosed === "hide" && !snapshotEnabled) {
    return null;
  }
  return (
    <button
      type="button"
      data-ndf-action={actionId}
      className={className}
      title={title || action.clauseRefs.join(" ")}
      disabled={!can}
      onClick={onClick}
    >
      {action.label}
    </button>
  );
}
