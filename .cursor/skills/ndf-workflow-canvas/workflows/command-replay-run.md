# Command Replay Run

Orchestrates `/ndf-command-replay-run`. Catalog id: `command-replay-run`.
Creates an isolated worktree at button-action baseline A and re-runs the recorded
button Prompt. Page click is instructions only — MUST NOT claim 已回放.

## Command

`/ndf-command-replay-run`

## Unique CLI

```bash
python3 spec/meta/tools/ndf_replay.py command-replay \
  --button-action <id> --baseline <A>
```

## Sequence

1. Read focused button action (`baselineSha`, `prompt`) from snapshot.
2. `git worktree add -b replay/<id>/<ts> tmp/ndf-command-replay/... <A>` — branch stops at A (no later commits).
3. MUST NOT checkout the user's live working branch.
4. Inside the worktree, execute the recorded original button Prompt.
5. Record HEAD / `git status` / `git diff` vs A (optional: update button-action `replayHead`).
6. MUST NOT claim 已回放 on the Commander page.
