# OpenClaw Control delegation

Canvas Control actions delegate NDF document-flow work to the configured OpenClaw
conductor session. Read `session_key` from `AGENTS.md`; never hardcode.

## Bridge sequence (Composer)

```text
1. Run: python3 spec/meta/tools/ndf_workflow_status.py control-pack --topic <topic> --task <task> --episode <episode-id> --json
2. If safe_to_delegate is false, stop and report blockers.
3. Cite `manifest_sha`, OpenClaw `context_plan.plan_sha` and `episode_id`; run context-verify; stop/recompile on drift.
4. Call MCP openclaw.chat_send with session_key from the pack and the task template below.
5. The message MUST include workspace.repo_root and workspace.active_topic from the pack.
6. Ask OpenClaw to persist workspace to .openclaw/state.json before file operations.
7. Summarize OpenClaw reply: gaps, files touched, next human phrase and bound receipt.
8. Do NOT approve gates or dispatch Claude Code unless the user explicitly asks.
9. Record the request/response and available tool observations in the same Episode. If only
   messages are visible, mark coverage=`messages_only`. Use
   `ndf_workflow_status.py message-record --role openclaw --direction request|response
   --coverage messages_only --episode <episode-id> --file <bound-message.json>`.
   Session keys remain encrypted provenance and are removed by share-safe export.
```

## Workspace binding (all tasks)

Every control-pack carries:

```json
"workspace": {
  "repo_root": "/absolute/path/to/repo",
  "repo_name": "hnsw-predictor-ndf",
  "repo_head": "git-sha",
  "active_topic": "bfs-cluster",
  "topic_dir": "poc/bfs-cluster/",
  "topic_ndf_dir": "poc/bfs-cluster/ndf/"
}
```

OpenClaw MUST on receive:

1. Read `{workspace.repo_root}/.openclaw/state.json` if it exists.
2. Compare `workspace.repo_root` / `repo_head` with the pack; if drifted, note in reply.
3. Write/update `{repo_root}/.openclaw/state.json` → `workspace` and `active_topic` before touching files.
4. Resolve all relative paths under `workspace.repo_root` (never assume process cwd).
5. If `repo_root` differs from prior binding, switch project and tell the user.
6. Verify the exact Manifest + OpenClaw role plan SHA before work and obey its ordered reads,
   graph slice and privileges. A Claude-role plan shown in Canvas is human preview only;
   derive the OpenClaw plan from the shared manifest via control-pack.

Do not use global `~/.openclaw/agents/...` as project state.

## legacy_gate_audit

```text
【track=poc】【control=legacy_gate_audit】topic: <topic>
session_key: <from control-pack>
phase_hint: <phase_hint>

You are OpenClaw. Read required_reads from the control-pack on demand — do not preload all of spec/.
Task: audit a legacy POC binder missing GATES.md receipts.

1. Read META-010, BEH-025 and poc/<topic>/ndf/* binder files listed in required_reads.
2. Report: gate states, binder gaps (design/implementation/test), perf bind errors, surface conflicts.
3. MAY draft poc/<topic>/ndf/GATES.md from the POC template with status=pending and empty approved_by.
4. MUST NOT set approved_by or claim gates are approved.
5. Return: gap summary, files created/changed, exact next human phrase (e.g. TOPIC已审核).

Control-pack JSON:
<embed control-pack output>
```

All mutating Control replies use the bound receipt fields from META-012:
`schema/task/topic/mode/step/repo_head/source_generation_sha/manifest_sha/context_plan_sha/command/`
`input_sha/output_sha/evidence_paths/started_at/finished_at/result/blockers`.

## gate_sha_audit

```text
【track=poc】【control=gate_sha_audit】topic: <topic>
session_key: <from control-pack>

Compare each gate receipt in GATES.md against canonical bundle SHA from control-pack.
Report valid / missing / legacy_unknown / invalidated per gate.
Do not append approved receipts. Return next_human_phrase if a gate is ready for human review.

Control-pack JSON:
<embed control-pack output>
```

## gate_receipt_draft

```text
【track=poc】【control=gate_receipt_draft】topic: <topic>
session_key: <from control-pack>

Prepare the next pending gate bundle summary for human review.
List bundle paths, content SHA, and the exact phrase the human must send.
Do not write approved_by. Return the phrase prominently.

Control-pack JSON:
<embed control-pack output>
```

## binder_amend

```text
【track=poc】【control=binder_amend】topic: <topic>
session_key: <from control-pack>

Revise DESIGN / INTERFACE / PERF_BASELINE per the user's business discussion.
Only write under poc/<topic>/ndf/. Gate receipts remain pending until human phrases.
After substantive amend, note which gates need re-review.

Control-pack JSON:
<embed control-pack output>
```

## control_proposal

```text
【track=process|poc】【control=control_proposal】topic: <topic>
session_key: <from control-pack>

Draft or revise spec/open/ or spec/meta/open/ proposal per AGENTS.md track routing.
Do not land stable clauses without 已确认/已审核. Return proposal path and next step.

Control-pack JSON:
<embed control-pack output>
```

## Project NDF improvement proposal

NDF Control uses a project-scoped pack, not a topic control-pack:

```text
python3 spec/meta/tools/ndf_workflow_status.py project-control-pack \
  --task ndf_improvement_proposal --json
```

OpenClaw reads the structured `spec_health.findings`, may run the listed Advisor
commands read-only, and drafts one focused `track=process` proposal under
`spec/meta/open/`. It MUST NOT edit stable `spec/meta/` body or product implementation,
and stops at the human phrase `已确认`.

## Write boundary (all tasks)

| Allowed | Forbidden |
|---------|-----------|
| `poc/<topic>/ndf/` | `src/`, `include/`, `tests/` |
| `spec/open/`, `spec/meta/open/` | `spec/meta/` stable body |
| `.openclaw/state.json` | Silent `GATES.md` approval |
