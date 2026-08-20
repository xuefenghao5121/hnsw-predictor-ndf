#!/usr/bin/env bash
# afterShellExecution: when control-pack|repair-pack|pack succeeds with
# safe_to_dispatch, send OpenClaw / Claude Code ACP, wait for result, then
# completion-record → action-commit → snapshot.
# Fail-open on send failure (writes tmp/ndf-dispatch-last.json). Never treats
# sent/acknowledged alone as commander success.
set -u
input="$(cat || true)"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT" || {
  printf '%s\n' '{}'
  exit 0
}

python3 - "$ROOT" "$input" <<'PY' || true
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
raw = sys.argv[2] if len(sys.argv) > 2 else "{}"
sys.path.insert(0, str(root / "spec" / "meta" / "tools"))
try:
    import ndf_dispatch_send as dispatch
    import ndf_workflow_status as workflow
except Exception:
    sys.exit(0)

try:
    hook = json.loads(raw) if raw.strip() else {}
except json.JSONDecodeError:
    hook = {}

command = str(
    hook.get("command")
    or hook.get("cmd")
    or hook.get("shellCommand")
    or ""
)
stdout = str(
    hook.get("output")
    or hook.get("stdout")
    or hook.get("result")
    or ""
)
# Only pack-producing CLIs.
if not any(
    token in command
    for token in (
        " control-pack",
        " project-control-pack",
        " genesis-pack",
        " repair-pack",
        " pack ",
        "ndf_workflow_status.py control-pack",
        "ndf_workflow_status.py project-control-pack",
        "ndf_workflow_status.py genesis-pack",
        "ndf_workflow_status.py repair-pack",
        "ndf_workflow_status.py pack",
    )
):
    sys.exit(0)
if " action-commit" in command or " snapshot" in command or "dispatch-send" in command:
    sys.exit(0)

pack = dispatch.extract_pack_from_shell_output(stdout)
if not pack:
    # Some hooks put output under nested keys.
    nested = hook.get("shellOutput") or hook.get("commandOutput") or ""
    if isinstance(nested, str):
        pack = dispatch.extract_pack_from_shell_output(nested)
if not pack:
    sys.exit(0)

# Resolve current commander hop for closeout.
catalog_action_id = None
action_id = None
try:
    receipts = workflow.read_action_receipts()
    started = next(
        (
            receipt
            for receipt in reversed(receipts)
            if receipt.get("status") == "started" and receipt.get("action_id")
        ),
        None,
    )
    if started:
        action_id = str(started.get("action_id"))
        catalog_action_id = str(started.get("catalog_action_id") or "").strip() or None
except Exception:
    pass

# Persist pack for debugging / manual dispatch-send.
pack_path = root / "tmp" / "ndf-dispatch-last-pack.json"
pack_path.parent.mkdir(parents=True, exist_ok=True)
pack_path.write_text(
    json.dumps(pack, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
    encoding="utf-8",
)

try:
    dispatch.dispatch_send(
        pack,
        catalog_action_id=catalog_action_id,
        action_id=action_id,
    )
except Exception as exc:
    # Fail-open: never block the shell path; leave evidence for humans.
    err = {
        "schema": "ndf-dispatch-send/v1",
        "state": "delivery_unknown",
        "dispatch_state": "delivery_unknown",
        "error": str(exc),
        "result_summary": f"dispatch_send exception: {exc}",
        "blockers": ["dispatch_send_exception"],
    }
    dispatch._write_last(err)
sys.exit(0)
PY

printf '%s\n' '{}'
exit 0
