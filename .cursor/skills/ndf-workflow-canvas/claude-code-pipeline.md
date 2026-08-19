# Claude Code pipeline contract

The repository-bound Claude Code ACP pipeline is the only implementation backend for this
Canvas. `poc/<topic>/` is a write policy; the pipeline supplies execution isolation.

Every start request MUST include `repo_root` from pack `workspace`. The worktree MUST lie
under `repo_root` (or be provably equivalent via realpath).

## Start request

```json
{
  "track": "bootstrap|poc|promote|bug|refactor|rollback",
  "repo_root": "/absolute/path/to/repo",
  "base_sha": "<git-sha>",
  "approved_content_sha": "<gate-bundle-sha>",
  "allowed_write_root": "<path-under-repo_root>",
  "forbidden": ["<path-or-contract>"],
  "context_pack": "<ndf-workflow pack JSON>"
}
```

## Required start response

```json
{
  "run_id": "<id>",
  "session_id": "<id>",
  "repo_root": "/absolute/path/to/repo",
  "base_sha": "<git-sha>",
  "worktree": "<isolated-path-under-repo_root>",
  "branch": "<branch>",
  "allowed_write_root": "<path>",
  "status": "running"
}
```

`worktree` MUST be under `repo_root` or provably equivalent. Missing or mismatched
`repo_root` / fields mean `unsafe`; do not dispatch writes. One topic may hold only
one active write `run_id` lease.

## Required completion response

```json
{
  "run_id": "<id>",
  "status": "completed|failed|aborted",
  "changed_files": [],
  "commit_sha": "<optional>",
  "reproduce": ["<command>"],
  "evidence_paths": [],
  "summary": "<text>"
}
```

After completion, run the relevant isolation/bind checks. Persist durable results only in
COMMITS/evidence; do not write runtime state into TOPIC or `.openclaw/state.json`.
