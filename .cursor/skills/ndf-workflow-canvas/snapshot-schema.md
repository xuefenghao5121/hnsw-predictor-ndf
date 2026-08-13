# Snapshot schema

`ndf_workflow_status.py snapshot --json` returns:

```json
{
  "schema": "ndf-workflow-snapshot/v2",
  "generated_at": "ISO-8601",
  "repo_head": "git-sha",
  "snapshot_sha": "sha256-of-local-workflow-evidence",
  "projection_freshness": {
    "state": "verified_at_generation|pending_refresh|refresh_in_progress|unknown",
    "latest_action": {},
    "receipt_path": "tmp/ndf-workflow-actions.jsonl"
  },
  "business": {
    "identity": {"name": "local product", "goal_summary": "...", "phase": "..."},
    "goals": [],
    "capabilities": [],
    "performance": {},
    "roadmap": [],
    "product_proposals": [],
    "topics": [],
    "risks": [],
    "now_next_blocked": {}
  },
  "control": {
    "genesis": {},
    "process_proposals": [],
    "close": {
      "state_source": "tree/git/tool-evidence",
      "topics": []
    },
    "spec_health": {
      "meta_clause_count": 0,
      "state": "not_run|current|stale",
      "checks": {},
      "findings": [],
      "next_actions": [],
      "proposal_plane_warnings": []
    },
    "gate_summary": {}
  },
  "runtime": {
    "implementation": {
      "provider": "claude-code-acp",
      "status": "unavailable|idle|running|failed",
      "default_session": "uuid",
      "pipeline_reachable": false,
      "active_runs": [],
      "workspace": {
        "binding": {"repo_root": "...", "state_path": ".openclaw/state.json"},
        "persisted": null,
        "state_exists": false
      }
    },
    "control": {
      "provider": "openclaw",
      "default_session_key": "agent:main:main",
      "reachable": null,
      "state_source": "gateway",
      "workspace": {
        "binding": {"repo_root": "...", "state_path": ".openclaw/state.json"},
        "persisted": null,
        "state_exists": false
      }
    }
  },
  "replay": {
    "schema": "ndf-replay-summary/v1",
    "state": "not_initialized|verified|invalid",
    "fsck": null,
    "episodes": []
  },
  "topics_detail": [],
  "selected_topic": null
}
```

The official Canvas payload also binds `payloadSha`, `absorbedActionId`,
`payloadBinding.repo_head` and `payloadBinding.source_generation_sha`.
It carries the same `replay` summary for the Replay tab.

`topics_detail[].health` adds:

```json
{
  "checks": {
    "perf_baseline": {"state": "passed|failed", "exit_code": 0},
    "isolation": {"state": "passed|failed", "exit_code": 0},
    "bindcheck": {"state": "passed|failed", "exit_code": 0}
  },
  "findings": [
    {
      "scope": "topic",
      "space": "Design|Implementation|Test",
      "kind": "machine-readable-kind",
      "severity": "error|warning|info",
      "evidence": "...",
      "repair_owner": "openclaw|claude-code|human",
      "repair_task": "...",
      "allowed_write_root": "...",
      "human_gate": null
    }
  ],
  "next_actions": [],
  "latest_diagnosis": {
    "state": "current|stale",
    "generated_at": "ISO-8601",
    "checks": {},
    "findings": []
  }
}
```

`topic-health --topic <t> --json` persists its report under
`tmp/ndf-workflow-health/topic-<t>.json`. `spec-health --json` persists
`tmp/ndf-workflow-health/spec.json`. These are derived evidence, never SoT.
Snapshot marks a persisted report stale when its source generation no longer matches.
Canvas compares current and latest-diagnosis finding keys by `kind + human_gate`, yielding
Resolved / Remaining / New without confusing diagnosis freshness with check pass/fail.

`snapshot --format canvas-json --probe-runtime --json` returns the official camelCase
`ndf-workflow-canvas-snapshot/v1` payload embedded by the Canvas. The Canvas MUST replace its
complete SNAPSHOT from this payload; partial ad-hoc snake_case conversion is not supported.

Proposal plane is path-based: `spec/open/` → `business.product_proposals` /
Canvas Product proposals; `spec/meta/open/proposal-meta-*.md` →
`control.process_proposals` / NDF Control. A `track: process` header on a product
file MUST NOT move it to Control. Path/track mismatches appear in
`control.spec_health.proposal_plane_warnings` and canvas-json
`control.proposalPlaneWarnings`.

## Action receipt and projection freshness

Canvas-originated operations that can change tree/git/tool evidence use:

```bash
ndf_workflow_status.py action-begin --operation <op> [--topic <topic>] --json
ndf_workflow_status.py action-finish --action-id <id> --result success|failed \
  [--blocker <reason>] --json
```

Receipts append to gitignored `tmp/ndf-workflow-actions.jsonl` as
`ndf-workflow-action/v2`, with monotonic `seq`, `prev_event_sha` and `event_sha`.
They are runtime audit evidence,
not NDF SoT. An old embedded Canvas cannot claim `fresh` after dispatch: local UI state first
shows `refresh_in_progress`, and only a newly generated official snapshot clears it.

## Close projection

`control.close.topics[]` is conservative and read-only:

```json
{
  "topic_id": "page-packer",
  "lifecycle": "exploring",
  "evidence_ready": true,
  "proposal_ready": false,
  "close_plan": {"state": "unknown", "ready": false, "source": null},
  "graphcheck": {"state": "unknown", "source": null},
  "verification": {"state": "unknown", "source": null},
  "finalization_ready": false,
  "steps": [
    {
      "id": "proposal",
      "plane": "Control",
      "label": "Promote/reject proposal reviewed",
      "status": "pending",
      "source": null
    }
  ],
  "next_step": "proposal",
  "blockers": ["close:reviewed_proposal_missing"]
}
```

Step status is limited to Canvas Todo states. Unknown graph/build/perf/golden remains
`pending`; dispatch does not change it. A persisted read-only plan is recognized at
`tmp/close-plan-<topic>-<mode>.md`.

Each business topic summary MAY include gate states and `next_human_phrase`:

```json
{
  "topic_id": "bfs-cluster",
  "phase_hint": "legacy_gate_audit",
  "gates": {
    "topic_review": {"state": "legacy_unknown", "phrase": "TOPIC已审核"},
    "design_review": {"state": "legacy_unknown", "phrase": "DESIGN已审核"},
    "implementation_approval": {"state": "legacy_unknown", "phrase": "可以开始实现"}
  },
  "next_human_phrase": "TOPIC已审核"
}
```

## control-pack schema

`ndf_workflow_status.py control-pack --topic <t> --task <task> --json`:

```json
{
  "schema": "ndf-control-pack/v2",
  "topic": "bfs-cluster",
  "task": "legacy_gate_audit",
  "provider": "openclaw",
  "session_key": "agent:main:main",
  "workspace": {
    "repo_root": "/absolute/path/to/repo",
    "repo_name": "hnsw-predictor-ndf",
    "repo_head": "git-sha",
    "state_path": ".openclaw/state.json",
    "active_topic": "bfs-cluster",
    "topic_dir": "poc/bfs-cluster/",
    "topic_ndf_dir": "poc/bfs-cluster/ndf/"
  },
  "phase_hint": "legacy_gate_audit",
  "gates": {},
  "binder_gaps": {},
  "required_reads": ["META-010", "BEH-025"],
  "allowed_write_roots": [],
  "forbidden": [],
  "next_human_phrase": "TOPIC已审核",
  "safe_to_delegate": true,
  "blockers": []
}
```

## Context Plan and pack v2

`ndf_workflow_status.py pack --topic <t> --json`:

```json
{
  "schema": "ndf-workflow-pack/v2",
  "topic": "bfs-cluster",
  "provider": "claude-code-acp",
  "workspace": {
    "repo_root": "/absolute/path/to/repo",
    "repo_name": "hnsw-predictor-ndf",
    "repo_head": "git-sha",
    "state_path": ".openclaw/state.json",
    "active_topic": "bfs-cluster",
    "topic_dir": "poc/bfs-cluster/",
    "topic_ndf_dir": "poc/bfs-cluster/ndf/"
  },
  "task_manifest": {
    "schema": "ndf-task-manifest/v1",
    "manifest_sha": "sha256"
  },
  "manifest_sha": "sha256",
  "context_plan": {
    "schema": "ndf-context-plan/claude-code/v1",
    "manifest_sha": "sha256",
    "role": "claude-code",
    "task": "poc_implementation",
    "track": "poc",
    "topic": "bfs-cluster",
    "plan_sha": "sha256",
    "ordered_reads": [],
    "seed_ids": [],
    "graph": {"nodes": [], "truncated": [], "blockers": []},
    "implementation_surface": [],
    "baseline": {},
    "privileges": {}
  },
  "context_verify": {"valid": true, "plan_sha": "sha256"},
  "static_preflight_passed": true,
  "runtime_dispatch_ready": false,
  "allowed_write_root": "poc/bfs-cluster/",
  "required_handshake": ["run_id", "session_id", "base_sha", "repo_root", "worktree", "allowed_write_root"]
}
```

`static_preflight_passed` covers gate/perf/isolation/context verification.
`runtime_dispatch_ready` covers pipeline reachability, same-topic lease exclusion and the full
run/session/base/repo/worktree/branch/allowed-root handshake. `safe_to_dispatch` is never
interpreted without both dimensions and a verified Canvas projection.

## Replay summary

`replay.episodes[]` contains only derived local evidence:

```json
{
  "id": "ep-...",
  "state": "verified|invalid",
  "head": "object-sha",
  "topic": "topic-or-null",
  "task": "task",
  "manifestSha": "sha256",
  "planSha": "sha256",
  "coverage": {"runtime_stream": "full_stream|completion_only|messages_only"},
  "coverageGaps": [],
  "joinGaps": [],
  "semanticGaps": [],
  "historicalIntegrity": true,
  "historicalSemantics": true,
  "currentRestoreReady": false,
  "currentDispatchReady": false,
  "currentReadinessErrors": [],
  "manifestSummary": {
    "intent": "...",
    "businessGoal": "...",
    "seeds": ["META-013"],
    "graphNodes": 3
  },
  "contextSummary": {
    "role": "openclaw",
    "task": "episode_replay",
    "orderedReads": ["spec/meta/process.md"],
    "writeRoots": []
  },
  "branches": {
    "control": {"eventCount": 2, "eventTip": "sha256", "valid": true},
    "implementation": {"eventCount": 4, "eventTip": "sha256", "valid": true}
  },
  "observations": [
    {"kind": "tool", "name": "shell", "policy": "sandbox", "sha": "object-sha"}
  ],
  "changedFiles": ["poc/topic/file"],
  "gateEvents": [],
  "r2Outcome": "not_run|equivalent",
  "r2Profile": {
    "adapter": "bwrap",
    "network": "none",
    "commands": [],
    "allowedWriteRoots": []
  },
  "eventCount": 0,
  "levels": {"R0": true, "R1": false, "R2": false, "R3": true},
  "timeline": []
}
```

R0 requires valid encrypted objects, refs, parent DAG and every branch event chain, plus
complete manifest/plan joins for strict audit. R1 additionally requires recorded observations.
R2 capability requires a bound historical repo/context; execution requires an allowlisted
isolation adapter, recorded sandbox cassettes, explicit cost/side-effect confirmation and writes
an outcome event on a separate replay branch. R3 is always an explicit new commit/branch.
Absence of captured runtime surface is a coverage gap, not a green replay claim.
Historical fields use only recorded content-addressed evidence. Current readiness rechecks the live
checkout/worktree/gates and may be false while historical R0 remains true.

## Bound receipt schema

Receipts that can make dispatch or Close green use:

```text
schema | task | topic | mode | step | repo_head | source_generation_sha
manifest_sha | context_plan_sha | command | input_sha | output_sha | evidence_paths
started_at | finished_at | result | blockers
```

Short legacy receipts, NOTES-only evidence and reports without these bindings are
`legacy_unbound|unknown`; absent receipts are `missing`.

Gateway session store (`~/.openclaw/agents/...`) is NOT project state. Project state lives at
`{repo_root}/.openclaw/state.json`.

Each topic detail keeps independent dimensions:

```json
{
  "lifecycle": "exploring|blocked|promoted|rejected|closed|unknown",
  "phase_hint": "ui-only",
  "gates": {},
  "spaces": {
    "design": {"ready": false, "gaps": []},
    "implementation": {"ready": false, "gaps": []},
    "test": {"ready": false, "gaps": []}
  },
  "agent_run": {"status": "unknown", "state_source": "pipeline"},
  "delegation": {
    "safe_to_dispatch": false,
    "safe_to_delegate_control": true,
    "evaluated_at": "ISO-8601"
  },
  "delta": {"feature": null, "hotspot": null, "latest_round": null},
  "traceability": [],
  "health": {"blockers": [], "conflicts": [], "stale": false}
}
```

`phase_hint` and Canvas selection state are derived and never become NDF truth.

v1 `genesis` + `cockpit` is deprecated. Product and process proposals MUST never share one list.
