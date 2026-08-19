# Snapshot schema

`ndf_workflow_status.py snapshot --json` returns:

```json
{
  "schema": "ndf-workflow-snapshot/v2",
  "generated_at": "ISO-8601",
  "repo_head": "git-sha",
  "snapshot_sha": "sha256-of-local-workflow-evidence",
  "projection_freshness": {
    "state": "fresh|refresh_in_progress|stale_after_action|unknown",
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
    "focused_topic": null,
    "risks": [],
    "now_next_blocked": {}
  },
  "control": {
    "genesis": {},
    "kernel_map": {
      "available": true,
      "path": "spec/meta/graph.json",
      "clause_count": 0,
      "stable_summary": {},
      "seed_ids": [],
      "seeds": [],
      "missing_seeds": []
    },
    "process_proposals": [],
    "process_hop": null,
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
      "status": "unavailable|idle|active|failed",
      "default_session": "uuid",
      "pipeline_reachable": false,
      "cli_available": false,
      "doctor_ok": null,
      "resume_available": null,
      "probe_error": null,
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
    "state": "not_initialized|indexed|invalid",
    "storeRoot": ".ndf/replay",
    "fsck": null,
    "episodes": [],
    "focused": null
  },
  "topics_detail": [],
  "selected_topic": null
}
```

`--topic` is the **unique fat page**, not an extra detail. Default order:
CLI `--topic` → Canvas `business-topic` → first exploring topic. Closed POCs
are directory-skipped and MUST NOT run `topic_view`.

The official Canvas payload also binds `payloadSha`, `absorbedActionId`,
`payloadBinding.repo_head` and `payloadBinding.source_generation_sha`.
It carries the same `replay` summary for the Replay tab.

Canvas-json `business` splits Topics the same way Replay splits hops:

- `topics[]`: **directory rows only** (Product table + Topics selector). Fields:
  `id`, `path`, `lifecycle`, `hypothesis`, `surface`, `baseline`, `phase`,
  `nextHumanPhrase`, `gates.{state,phrase}`, `blockers`, `conflicts`,
  `spaces.ready`, `health.blockerCount`, `closeEligible`. No
  `task_manifest`, no graph `nodes[]`, no health evidence bodies.
- `focusedTopic` / `focusedTopicId`: **one** workbench (existing Topic shape,
  further slimmed). Null when nothing is exploring/blocked. Canvas selector
  `business-topic` that differs from `focusedTopicId` shows 「打开工作台」
  instead of treating the directory row as a workbench.
- Directory compile reads TOPIC header + GATES capsules. Only the focused id
  runs `topic_view(mode=canvas)` (shallow graph or health-cache reuse).
  Full `create_manifest(depth=8, bodies on)` stays on `pack` /
  `control-pack` / `repair-pack`.

`snapshotSha` / `payloadBinding.source_generation_sha` is the Merkle root of
layered fingerprints (`repo_head`, `meta`, `product`, `poc[topic]`, `replay`),
from git HEAD + dirty content hashes — not a full-tree byte hash. Unchanged
`meta` / `product` layers reuse persisted `spec-health` checks and MUST NOT
re-run `ndf_graphcheck`. `update-embedded` verifies the written payload SHA;
it MUST NOT compile `snapshot()` a second time. Explicit `--verify-embedded`
may still rebuild.

`topics_detail[].health` adds:

```json
{
  "checks": {
    "perf_baseline": {"state": "passed|failed", "exit_code": 0},
    "isolation": {"state": "passed|failed", "exit_code": 0},
    "bindcheck": {"state": "passed|failed", "exit_code": 0},
    "meta_graph": {"state": "passed|failed|not_run|stale", "exit_code": 0},
    "product_graph": {"state": "passed|failed|not_run|stale", "exit_code": 0}
  },
  "findings": [
    {
      "scope": "topic|project",
      "space": "Design|Implementation|Test",
      "kind": "machine-readable-kind",
      "severity": "error|warning|info",
      "evidence": "...",
      "why_blocked": "one sentence",
      "clause_refs": [{"id": "BEH-025", "title": "..."}],
      "source": "gate|health_check|synthetic",
      "repair_owner": "openclaw|claude-code|human",
      "repair_task": "...",
      "allowed_write_root": "...",
      "human_gate": null
    }
  ],
  "findings_by_space": {"Design": [], "Implementation": [], "Test": []},
  "next_actions": [],
  "latest_diagnosis": {
    "state": "current|stale",
    "generated_at": "ISO-8601",
    "checks": {},
    "findings": [],
    "finding_diff": {"resolved": [], "remaining": [], "new": []}
  }
}
```

Canvas Topics also projects **on `focusedTopic` only** (directory rows never carry these):

- `topic_overview`: `{ purpose, hypothesis, explore_surface, idea_sources, lifecycle }` from the TOPIC contract slice
- `ndfFoundation`: seed product clauses + `clause_count` + at most 12 `depends_on_edges` (no full graph bodies)
- `workflow_meta`: process/meta nodes and spec-health state
- `spaces.*.purpose` / `spaces.*.clause_refs`; Test may include `latest_round` / `delta_path` / `latest_verdict`
- `delegation.context_plan.ordered_reads`: first 5 + `read_count`; no Task Manifest
- `health.findings`: `kind/severity/why_blocked/clause_refs/repair_*` without long `evidence`
- Graphcheck: `health.checks.meta_graph` / `product_graph` come from project `spec_health` (ndf_graphcheck `--meta` / `--product`), not per-topic re-runs. Failures appear as Design findings `meta_graph_failed` / `product_graph_failed` with `scope=project`, and as `delegation.dispatch_blockers` `graphcheck_failed` / `spec_health_stale`.
- Canvas workbench compile is `graph_closure(depth=2, node_budget=32, include_bodies=false)` or a health-cache hit. Diagnose topic still runs full `topic-health`.

`topic-health --topic <t> --json` persists its report under
`tmp/ndf-workflow-health/topic-<t>.json`. `spec-health --json` persists
`tmp/ndf-workflow-health/spec.json`. These are derived evidence, never SoT.
Snapshot marks a persisted report stale when its source generation no longer matches.
Canvas shows diagnosis freshness only as a one-line strip on **阻塞与修复**; it is not a blocker.

`snapshot --format canvas-json --probe-runtime --json` returns the official camelCase
`ndf-workflow-canvas-snapshot/v1` payload embedded by the Canvas. The Canvas MUST replace its
complete SNAPSHOT from this payload; partial ad-hoc snake_case conversion is not supported.

Canvas-json `business.performance` includes `goldenHeadStatus`
(`aligned` | `docs_only_ahead` | `head_ahead_of_golden` | `missing` | `golden_unresolvable`)
and `trunkChangedSinceGolden` (Trunk `src/` `include/` `tests/` paths that differ from the
Golden commit). Product New Proposal requires `fresh` and `aligned` or `docs_only_ahead`.

Proposal plane is path-based: `spec/open/` → `business.product_proposals` /
Canvas Product proposals; `spec/meta/open/proposal-meta-*.md` →
`control.process_proposals` / NDF Control. A `track: process` header on a product
file MUST NOT move it to Control. Path/track mismatches appear in
`control.spec_health.proposal_plane_warnings` and canvas-json
`control.proposalPlaneWarnings`.

Canvas-json `control` also projects:

- `kernelMap`: `{ available, path, clause_count, stable_summary, seed_ids, seeds, missing_seeds }` from `spec/meta/graph.json` only (required Control seeds: META-001…005, META-008…015, CHR-008, BEH-018…020, BEH-025, CON-POC-001). `nodes` is omitted (seeds are the map; do not duplicate). Control UI leads with seed coverage / missing seeds, not product clause counts. Do not merge `spec/graph.json` product nodes.
- `nextActions`: copy of `spec_health.next_actions`
- `genesis.accepted`, `genesis.genesis_trunk_sha`, `genesis.install_needed`, `genesis.kernel_installed`
- `processProposals`: `[title, hop|status, path][]` tuples, **only** waiting hops (`waiting_confirm` / `waiting_review` / managed `confirm_land` / `review`) and managed Implemented-未审核 (`implemented_pending_review`). Historical Implemented files without META-014 receipts are `processProposalArchivedCount`, not catalog rows.
- `processHop`: `{ focusedPath, title, hop, nextHumanPhrase, remaining }` or `null`. Prefer latest `waiting_confirm`, else latest `waiting_review`. Canvas 工作流演进 uses this for the 推进 CTA.
- `control.close.topics[]`: fat close branch only for the focused topic; other directory rows carry `closeEligible` only.
- `business.identity.charterExists`: false → Canvas default tab is NDF Control

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

`control.close` is snapshot evidence, not a Canvas tab. Topics projects it after a
close `selected_decision`. `control.close.topics[]` is conservative and read-only:

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
`tmp/close-plan-<topic>-<mode>.md`. The plan header MAY include
`trunk_src_writes: none|required`. When `none`, integrate is N/A and
`next_step` skips it. Canvas recovery for reject N/A is 「继续关闭收口」.

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

The ledger SoT is `<repo>/.ndf/replay` (ReplayStore). Canvas is a counter: it
embeds a slim hop **directory** plus **one** focused ledger page. It MUST NOT
copy every hop's Prompt/timeline into `const SNAPSHOT`.

Query on disk:

```bash
python3 spec/meta/tools/ndf_replay.py canvas-index --json
python3 spec/meta/tools/ndf_replay.py canvas-ledger --episode <id> --json
python3 spec/meta/tools/ndf_workflow_status.py snapshot \
  --update-embedded <tsx> --replay-episode <id> --json
```

Routine `--update-embedded` MUST NOT pass `--probe-runtime`. Header Refresh snapshot
is the only probe, and MUST pass `--topic <selected>` so the workbench stays focused.

Embed budget: compact SNAPSHOT JSON MUST stay ≤ 120KB (fail-closed). Per-bucket
caps: `topics_directory` 24KiB, `focused_topic` 24KiB, `control` 20KiB,
`replay_directory` 16KiB, `focused_ledger` 16KiB, `other` 20KiB. Overflow MUST
name the overflowing bucket (`canvas snapshot exceeds 122880 (total=…,
focused_topic=…>24576)`). Do not raise the total cap to embed every workbench.

`replay.episodes[]` is directory-only (no Prompt text, no timeline, no `kinds` /
`participants`). If the directory still exceeds its bucket, keep the newest rows
and set `omittedCount`. That is directory truncation, not embedding Prompts.

```json
{
  "id": "ep-...",
  "title": "meta-proposal · 确认落地 · 2026-08-17",
  "plane": "meta|project",
  "agent": "openclaw",
  "happenedAt": "ISO-8601",
  "resultLine": "门禁 · 下达",
  "topic": "topic-or-null",
  "task": "task",
  "canRestoreRecord": true,
  "state": "indexed"
}
```

`replay.focused` is the opened hop (same fields as the former fat episode card,
including `assembledPrompt` / `dispatchedPrompt` / slim `timeline`). Missing
focused, or `selected !== focused.id`, means the UI shows 「查这条账」 instead of
fake Prompt text.

Projection fields on the focused page: `humanUtterance`, `assembledContext`,
`assembledPrompt`, `dispatchedPrompt`, `promptDrift`, `readWhyMissing`,
`canRestoreRecord`, `dispatchLeak`.

`dispatchLeak=true` when a dispatch/request primary task is still raw human speech
(short-circuit). `promptDrift.mismatch=true` when the normative assembled Prompt and
the actual dispatched text disagree (`dispatch_human_leak`, `assembled_missing`,
`dispatched_missing`, `dispatch_unbound`). `assembledPrompt.text` is reconstructed
from recorded Manifest + Context Plan, never from live tree or graphNodes.
`dispatchedPrompt.text` is the recorded OpenClaw message or ACP handshake summary.
Missing either side MUST set `whyMissing`. `historicalSemantics` MUST fail closed on
leak. `canRestoreRecord` is historical object-chain readiness (not live `audit.valid`).
`orderedReads` MUST come from the Context Plan; when empty, `readWhyMissing` explains
planSha / blob / manifest-only. Canvas Replay MUST list readable paths (or the reason)
and the two Prompt panes; compare-episode UI is not part of the tab. Older snapshots
may omit the new fields; the Canvas treats them as optional.

CLI R0/R1/R2/R3 remain META-013 contracts. Canvas hop/prefix MUST run
`ndf_replay.py guest-run --adapter vm`, and accept only `ndf-replay-guest-proof/v1`
with `valid=true` (contract `adapter=vm`). MUST NOT host-mount the live checkout.
Lsoft (prompt) and Lns (worktree/bwrap/`isolate`) MUST NOT be shown as completed
replay. No KVM/image → `environment_blocked` (fail closed). Workspace write-back is
not a Canvas Replay action. MUST NOT surface R3.

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
