# Guest replay workflow

Orchestrates `/ndf-guest-replay`. Catalog ids: `guest-replay-hop`, `guest-replay-prefix`.

## Command

`/ndf-guest-replay`

## Unique CLI

```bash
python3 spec/meta/tools/ndf_replay.py guest-run --adapter vm
```

## Sequence

1. GIT INPUT checkout of `remote_branch` (host launcher; do not mutate product trees).
2. Unique CLI with `--episode <id> --commit <sha>`. Prefix variant reports only the selected timeline prefix.
3. Proof `ndf-replay-guest-proof/v1` with `adapter=vm`. MUST NOT host-mount live `repo_root`.
4. No KVM/image → `environment_blocked`, no soft fallback onto the live checkout.
5. Snapshot refresh is optional; do not treat replay as Canvas write-back.
