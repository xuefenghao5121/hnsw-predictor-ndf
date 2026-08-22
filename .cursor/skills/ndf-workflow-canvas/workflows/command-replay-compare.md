# Command Replay Compare

Orchestrates `/ndf-command-replay-compare`. Catalog id: `command-replay-compare`.
Opens a detached worktree at original result SHA B for side-by-side comparison.
Does not re-run the skill. Instructions only — MUST NOT claim 已回放.

## Command

`/ndf-command-replay-compare`

## Unique CLI

```bash
python3 spec/meta/tools/ndf_replay.py command-replay \
  --button-action <id> --baseline <A> --compare-sha <B> --compare-only
```

## Sequence

1. Read focused `baselineSha` / `resultSha` from snapshot.
2. Detach worktree at B (or show `git show --stat B` + `git diff A B` without checkout).
3. Do not re-run the original button skill.
4. MUST NOT claim 已回放.
