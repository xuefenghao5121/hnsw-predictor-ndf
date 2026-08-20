#!/usr/bin/env bash
# Local-only operational unblock for hotspot-optimization poc_measurement.
# Run on the host at /home/huawei/hnsw-predictor-ndf (not cloud /workspace).
# Retries on fork EAGAIN. Does not click gate/binder pipelines.
set -euo pipefail

ROOT="${1:-/home/huawei/hnsw-predictor-ndf}"
cd "$ROOT"

retry() {
  local n=0 delay=2
  while true; do
    if "$@"; then
      return 0
    fi
    n=$((n + 1))
    if [[ $n -ge 10 ]]; then
      echo "FAILED after $n attempts: $*" >&2
      return 1
    fi
    echo "retry $n (sleep ${delay}s): $*" >&2
    sleep "$delay"
    delay=$((delay * 2))
    if [[ $delay -gt 32 ]]; then delay=32; fi
  done
}

retry git fetch origin cursor/ndf-meta-integrate-pev95-063a
retry git checkout cursor/ndf-meta-integrate-pev95-063a
retry git pull --ff-only origin cursor/ndf-meta-integrate-pev95-063a

HEAD="$(git rev-parse HEAD)"
BOUND_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
mkdir -p .openclaw tmp

python3 - <<PY
import json
from pathlib import Path
from datetime import datetime, timezone
path = Path(".openclaw/state.json")
state = json.loads(path.read_text()) if path.is_file() else {}
head = "$HEAD"
bound_at = "$BOUND_AT"
state["workspace"] = {
    "repo_root": str(Path("$ROOT").resolve()),
    "repo_name": "hnsw-predictor-ndf",
    "repo_head": head,
    "state_path": ".openclaw/state.json",
    "bound_sha": head,
    "bound_at": bound_at,
    "active_topic": "hotspot-optimization",
}
state["last_activity"] = bound_at
path.write_text(json.dumps(state, indent=2) + "\n")
print(json.dumps(state.get("workspace"), indent=2))
PY

echo "=== light probe ==="
python3 - <<'PY'
import sys
sys.path.insert(0, "spec/meta/tools")
import ndf_workflow_status as w
import json
print("claude_light:", json.dumps(w.probe_claude_acp_light(refresh=True), default=str))
print("openclaw:", json.dumps(w.probe_openclaw(), default=str))
print("runtime_light:", json.dumps(w.runtime_status("light"), default=str))
PY

echo "=== finish orphan started actions ==="
python3 - <<'PY'
import json, subprocess, sys
from pathlib import Path
path = Path("tmp/ndf-workflow-actions.jsonl")
if not path.is_file():
    print("no actions ledger")
    sys.exit(0)
latest = {}
for line in path.read_text().splitlines():
    if not line.strip():
        continue
    ev = json.loads(line)
    aid = ev["action_id"]
    if aid not in latest or int(ev.get("seq") or 0) >= int(latest[aid].get("seq") or 0):
        latest[aid] = ev
started = [ev for ev in latest.values() if ev.get("status") == "started"]
print(f"started_count={len(started)}")
for ev in started:
    aid = ev["action_id"]
    print("finishing", aid, ev.get("operation"))
    subprocess.check_call([
        "python3", "spec/meta/tools/ndf_workflow_status.py",
        "action-finish", "--action-id", aid,
        "--result", "cancelled", "--blocker", "orphaned_plan_unblock", "--json",
    ])
PY

retry python3 spec/meta/tools/ndf_workflow_status.py snapshot --out tmp/ndf-canvas-snapshot.json --json > tmp/ndf-canvas-snapshot.stdout.json
python3 - <<'PY'
import json
from pathlib import Path
d = json.loads(Path("tmp/ndf-canvas-snapshot.stdout.json").read_text())
pf = d.get("projectionFreshness") or {}
print("projectionFreshness.state=", pf.get("state"))
print("absorbedActionId=", d.get("absorbedActionId"))
print("in_progress=", pf.get("in_progress"))
PY

echo "=== action-begin + repair-pack ==="
BEGIN="$(retry python3 spec/meta/tools/ndf_workflow_status.py action-begin --operation poc_measurement --catalog-action-id poc-measurement --topic hotspot-optimization --json)"
echo "$BEGIN" | tee tmp/hotspot-poc-measurement-begin.json
ACTION_ID="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["action_id"])' <<<"$BEGIN")"

retry python3 spec/meta/tools/ndf_workflow_status.py repair-pack --topic hotspot-optimization --task poc_measurement --json | tee tmp/hotspot-poc-measurement-repair-pack.json

python3 - <<'PY'
import json, shutil, subprocess
from pathlib import Path
pack = json.loads(Path("tmp/hotspot-poc-measurement-repair-pack.json").read_text())
print("safe_to_dispatch=", pack.get("safe_to_dispatch"))
print("static_preflight_passed=", pack.get("static_preflight_passed"))
print("runtime_dispatch_ready=", pack.get("runtime_dispatch_ready"))
print("blockers=", pack.get("blockers"))
print("context_verify.valid=", (pack.get("context_verify") or {}).get("valid"))
print("context_verify.errors=", (pack.get("context_verify") or {}).get("errors"))
cli = bool(shutil.which("claude"))
print("claude_cli=", cli)
# dispatch-send may not exist; only attempt if documented CLI present and safe
help_txt = subprocess.run(
    ["python3", "spec/meta/tools/ndf_workflow_status.py", "-h"],
    text=True, capture_output=True, check=False,
).stdout
has_dispatch = "dispatch-send" in help_txt
print("dispatch_send_cli=", has_dispatch)
if pack.get("safe_to_dispatch") and cli and has_dispatch:
    begin = json.loads(Path("tmp/hotspot-poc-measurement-begin.json").read_text())
    subprocess.check_call([
        "python3", "spec/meta/tools/ndf_workflow_status.py",
        "dispatch-send",
        "--pack-file", "tmp/hotspot-poc-measurement-repair-pack.json",
        "--catalog-action-id", "poc-measurement",
        "--action-id", begin["action_id"],
        "--json",
    ])
else:
    print("STOP after pack; leave for Command Agent hook")
PY

echo "DONE local unblock at $ROOT HEAD=$HEAD"
