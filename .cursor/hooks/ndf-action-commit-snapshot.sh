#!/usr/bin/env bash
# Fail-open stop hook: if a commander hop started and has no button-action yet,
# run action-commit + snapshot. Never dispatches OpenClaw/ACP.
# Prefer afterShellExecution dispatch-send closeout for pack hops; this only
# backfills when that path did not record a button-action.
set -u
input="$(cat || true)"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT" || {
  printf '%s\n' '{}'
  exit 0
}

python3 - "$ROOT" <<'PY' || true
import json
import subprocess
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root / "spec" / "meta" / "tools"))
try:
    import ndf_actions  # noqa: F401
    import ndf_replay
    import ndf_workflow_status as workflow
except Exception:
    sys.exit(0)

receipts = workflow.read_action_receipts()
started = next(
    (
        receipt
        for receipt in reversed(receipts)
        if receipt.get("status") == "started" and receipt.get("action_id")
    ),
    None,
)
if not started:
    sys.exit(0)

action_id = str(started.get("action_id"))
catalog_id = str(started.get("catalog_action_id") or "").strip()
if not catalog_id:
    # Without catalog id, refuse to guess among shared operations.
    sys.exit(0)

store = ndf_replay.ReplayStore(root)
already = any(
    str(item.get("workflowActionId") or "") == action_id
    for item in ndf_replay.list_button_actions(store)
)
if already:
    sys.exit(0)

prompt_rel = ndf_actions.action_prompt_relpath(catalog_id)
cmd = [
    "python3",
    "spec/meta/tools/ndf_workflow_status.py",
    "action-commit",
    "--action-id",
    action_id,
    "--catalog-action-id",
    catalog_id,
    "--prompt-file",
    prompt_rel,
    "--json",
]
commit = subprocess.run(
    cmd,
    cwd=root,
    check=False,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)
# Fail open: never block the agent stop path.
if commit.returncode == 0:
    subprocess.run(
        [
            "python3",
            "spec/meta/tools/ndf_workflow_status.py",
            "snapshot",
            "--out",
            "tmp/ndf-canvas-snapshot.json",
            "--json",
        ],
        cwd=root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
sys.exit(0)
PY

printf '%s\n' '{}'
exit 0
