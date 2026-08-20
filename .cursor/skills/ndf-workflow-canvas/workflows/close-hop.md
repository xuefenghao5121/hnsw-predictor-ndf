# Close hop workflow

Orchestrates `/ndf-close-hop`. Catalog ids: `generate-next-step`, `next-close-hop`.
Not silent promote. Contract: [close-console.md](../close-console.md).

## Command

`/ndf-close-hop`

## Unique CLI

```bash
python3 spec/meta/tools/ndf_close.py plan --topic <topic> --mode <promote|partial|reject>
```

## Delegate

OpenClaw for proposal/finalize hops; Claude Code ACP only when
`trunk_src_writes=required`. See [acp-delegate.md](../acp-delegate.md).

## Sequence

1. GIT INPUT checkout of `remote_branch`.
2. Map human text to `selected_decision`. Empty MUST NOT default to `continue_exploring`.
3. implement / continue_exploring: record decision only; do not delegate from this hop.
4. reject / promote / partial: record `selected_decision`, then first legal close hop in the same chat (`control_proposal` if unreviewed, else close-apply).
5. Run unique CLI (`ndf_close.py plan` / `close-plan --json`). Read-only; no apply.
6. After **已审核**, continue the apply chain in this chat. Topics 「继续关闭收口」 is recovery only.
7. Promote is never silent. Reject defaults to `trunk_src_writes=none`.
8. One POST_ACTION_SYNC at the end + snapshot refresh.
