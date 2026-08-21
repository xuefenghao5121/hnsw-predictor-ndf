#!/usr/bin/env bash
# Fail-open stop hook: if a commander hop started and was not dispatched
# (waiting_human / pack error / abandoned), action-finish cancelled + snapshot --out.
# Ready packs awaiting human 「派发」 are skipped (awaiting_human_dispatch).
# Never dispatches OpenClaw/ACP. Skip when dispatch-send is still in flight.
set -u
input="$(cat || true)"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT" || {
  printf '%s\n' '{}'
  exit 0
}

python3 - "$ROOT" <<'PY' || true
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root / "spec" / "meta" / "tools"))
try:
    import ndf_workflow_status as workflow
except Exception:
    sys.exit(0)

try:
    workflow.close_unsent_started_action()
except Exception:
    sys.exit(0)
sys.exit(0)
PY

printf '%s\n' '{}'
exit 0
