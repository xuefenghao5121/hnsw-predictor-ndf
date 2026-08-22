# Claude Code delegation

All tracks require `repo_root` from pack `workspace`. Worktree MUST be under `repo_root`.
Resolve relative paths under `repo_root`, never assume process cwd.
All prompts MUST cite `manifest_sha`, the Claude `context_plan.plan_sha`, and `episode_id`;
the Agent MUST run context-verify before work and stop/recompile only if
`context-verify.valid` is false (contract / expected_content_sha change). Do not stop
on slice_manifest_sha inequality when content SHA matches. Role plans differ,
but OpenClaw/Claude/Canvas MUST share the same manifest parent.

## Runtime lease handshake

Before any write, require `run_id`, `session_id`, `base_sha`, `repo_root`, isolated
`worktree`, `branch` and `allowed_write_root`. Record `run_id` as the same-topic lease in
gitignored runtime evidence and the same Episode. `lease-record` MUST resolve the exact latest
lease-eligible dispatch `pack_sha` (`safe_to_dispatch` **or** static-ready
`safe_to_delegate` / `static_preflight_passed`); file-imported leases are revalidated against that pack, manifest,
plan, base SHA, worktree and allowed root. The Episode also records `acp.start`,
`lease.acquired|released` and `refs/runs/<run-id>`.
If static preflight is true but there is no active isolated lease, only
prepare this lease: create a worktree under `repo_root`, `lease-record` into
`tmp/ndf-workflow-leases.jsonl`, refresh the official projection, and do not
start implementation. ACP reachable is not a lease. A lease_only stub without
`run_id` / `worktree` MUST NOT count as acquired.

After `git worktree add`, the lease-prep path (`dispatch-send` /
`_prepare_isolated_lease`) MUST symlink main-repo **gitignored local deps** the
worktree needs for build/measure (default: `hnswlib`, `output`, and ignored
children under `data/` such as `*.fvecs` / `*.bin`). Tracked files under `data/`
stay as the worktree checkout; do not replace them. Ensure empty writable
`build/` and `results/` exist. Override roots with env `NDF_LEASE_LOCAL_DEPS`
(comma-separated). MUST NOT copy large blobs; MUST NOT commit those links.
Workers MUST use the lease worktree paths (follow the symlinks) rather than
falling back to the commander tree.

## bootstrap

```text
【track=bootstrap】mode: <greenfield|adopt>
repo_root: <absolute path from pack.workspace>
Read the approved Genesis pack and gate bundle.
Work only in the isolated worktree under repo_root returned by the pipeline.
May write initial src/include/tests/build config and L2/L3.
Must not modify L0/L1, charter, architecture, decisions, spec/meta.
Build the smallest vertical slice; unknown mechanisms remain future POCs.
Return changed files, candidate commit, build/test commands and evidence.
```

## poc

```text
【track=poc】topic: <topic>
repo_root: <absolute path from pack.workspace>
Approved content SHA: <sha>
Context plan SHA: <context_plan.plan_sha>
Manifest SHA: <manifest_sha>
Episode ID: <episode_id>
Only write: poc/<topic>/ (under repo_root)
Forbidden: src/, include/, tests/, stable SLA, spec/meta/, production patches in spec/models/.
Read: TOPIC → DESIGN → PERF_BASELINE → DELTA → INTERFACE → GATES → proposals.
Write evidence to poc/<topic>/ndf/evidence/ and update DELTA/COMMITS as required.
Return changed files, commit, reproduction commands and evidence paths.
Return SHA-256 for every changed file, the evidence bundle SHA, and evidence-bound receipts for
the required isolation/topic-health/perf post-checks.
Return a bound completion receipt containing source generation, context plan SHA,
command/input/output SHAs, evidence paths, times, result and blockers.
When the round needs a human next decision, the completion MUST also include
`decision_briefing`: summary, verdict, decision_path[], and optional
`suggested_paths[]` (mode/recommended/label/rationale/next_work/prefill) copied from
the worker markdown Decision path. Do not leave those choices only in prose.
Record available ACP/model/tool events under the Episode. If only completion is visible,
set coverage=`completion_only`; do not synthesize a full stream.
Then Composer MUST run POST_DISPATCH_SYNC: completion-record, lease release if still
active, topic-health, official Canvas snapshot --update-embedded (no --probe-runtime). Tell the human to read
the Topics **decision briefing** and write the next decision there. A worker markdown
report is not the command surface and is not an NDF close.
```

## bounded POC repair

Use `repair-pack --topic <topic> --task poc_prepare_baseline|poc_isolation_repair|poc_measurement`.

Command Agent runs `repair-pack` (writes `tmp/ndf-dispatch-last-pack.json`), reports
the pack summary, and **waits for human 「派发」/「继续」** in the same chat. Then:

```bash
python3 spec/meta/tools/ndf_workflow_status.py dispatch-send \
  --pack-file tmp/ndf-dispatch-last-pack.json \
  --catalog-action-id <id> --action-id <uuid> --json
```

`dispatch-send` sends the pack to Claude Code ACP and waits with heartbeat
(`NDF_ACP_PING_SEC` / `STALL_SEC` / `MAX_SEC`) on resume artifacts, disk
completion, and stdout notify — not a single 900s wall timeout. Then
`completion-record` → (`action-commit` only if succeeded) → `action-finish`
→ write last.json → `snapshot --out`.
In-flight, human 「进展如何」 runs `dispatch-probe` (liveness / refresh stall /
closeout if receipt landed). Do not `dispatch-send` the same pack again.
Stdout is notify-only; the disk file MUST include handshake
(`worktree` / `branch` / `run_id` / `session_id`) plus `changed_files` and
`reproduce_commands`. MUST NOT treat stdout `ndf-agent-completion/v1` as the
validated receipt.
MUST NOT rely on Cursor `afterShellExecution` to auto-send.
Commander-approved packs inherit ACP permission bypass; humans MUST NOT be
sent into the Claude Code session to click Bash approve.
`execution_binding_stale` is not a measurement blocker.

- `poc_prepare_baseline` is delegated when the Implementation gap `missing_baseline_workspace`
  exists. Claude MUST copy the INTERFACE implementation slice and the required Trunk
  baseline `.h/.cpp` into `poc/<topic>/` to form a buildable R0-aligned baseline
  workspace. MUST NOT run measurement, MUST NOT amend PERF Numbers/DELTA, and MUST
  not touch Trunk `src/`, `include/`, `tests/` or rewrite git history.
- `poc_isolation_repair` may be delegated while normal implementation pack is blocked,
  but Claude may only repair/copy inside `poc/<topic>/`; Trunk cleanup or git history
  disposition requires human approval.
- `poc_measurement` requires a valid implementation gate and a complete perf bind
  skeleton (`vs` / `config_id` / `measure_script`). Unverified or pending Numbers are
  the measurement input state, not a dispatch blocker. OpenClaw `binder_amend` cannot
  write PERF Numbers or clear `unverified_measurement_claim`.
- All repair tasks MUST run the repair pack `post_checks`. `dispatch-send` owns
  POST_DISPATCH_SYNC (`completion-record`, lease release if active, Canvas snapshot).
  Do not treat `sent` as success.

## promote

```text
【track=promote】topic: <topic>
repo_root: <absolute path from pack.workspace>
Require reviewed promote proposal and read-only close plan.
Read landed stable L1; implement the minimum clean Trunk slice under repo_root.
May write src/include/tests/50-verification and L2/L3/field-level definitions.
Must not modify L0/L1, charter, architecture, decisions, spec/meta.
Do not mark TOPIC promoted or archive before index/graph/build/perf/golden are green.
Return changed files, commits and verification evidence.
```
