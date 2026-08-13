# Claude Code delegation

All tracks require `repo_root` from pack `workspace`. Worktree MUST be under `repo_root`.
Resolve relative paths under `repo_root`, never assume process cwd.
All prompts MUST cite `manifest_sha`, the Claude `context_plan.plan_sha`, and `episode_id`;
the Agent MUST run context-verify before work and stop/recompile on drift. Role plans differ,
but OpenClaw/Claude/Canvas MUST share the same manifest parent.

## Runtime lease handshake

Before any write, require `run_id`, `session_id`, `base_sha`, `repo_root`, isolated
`worktree`, `branch` and `allowed_write_root`. Record `run_id` as the same-topic lease in
gitignored runtime evidence and the same Episode. `lease-record` MUST resolve the exact latest
verified dispatch `pack_sha`; file-imported leases are revalidated against that pack, manifest,
plan, base SHA, worktree and allowed root. The Episode also records `acp.start`,
`lease.acquired|released` and `refs/runs/<run-id>`.
If static preflight is true but runtime readiness is false, only
prepare this lease, write the bound lease receipt, refresh the official projection, and do not
start implementation.

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
Record available ACP/model/tool events under the Episode. If only completion is visible,
set coverage=`completion_only`; do not synthesize a full stream.
```

## bounded POC repair

Use `repair-pack --topic <topic> --task poc_isolation_repair|poc_measurement`.

- `poc_isolation_repair` may be delegated while normal implementation pack is blocked,
  but Claude may only repair/copy inside `poc/<topic>/`; Trunk cleanup or git history
  disposition requires human approval.
- `poc_measurement` requires a valid implementation gate and complete perf bind.
- Both tasks MUST run the repair pack `post_checks`, then `topic-health`, before refresh.

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
