# Close hop contract

There is no Close tab. Close is a Topics prompt sequence after
`selected_decision ∈ {reject, promote, partial}`. `newComposerChat` is fire-and-forget;
dispatched is never completed.

**生成下一步** for close MUST record `selected_decision`, then execute the first legal
hop in the same chat: `control_proposal` if the close proposal is unreviewed, otherwise
the **close-apply chain**. After **已审核**, continue that chain in the same chat.
MUST NOT send the human back to Topics between plan, N/A integrate skip, graphcheck,
and finalize. Topics “继续关闭收口” is only a recovery button if the human left the
chat or the chain stopped on ACP / a blocker. MUST NOT say "open the Close page".

Human pauses remain **已确认** and **已审核**. ACP pauses only when
`trunk_src_writes=required` (`src/` / `include/` / `tests/`). Reject defaults to
`trunk_src_writes=none`.

Every close prompt MUST include the NDF hop contract: the apply chain (or one
proposal/ACP pause), write boundary, human gate if any, POST_ACTION_SYNC, and
whether the next work stays in this chat.

## Steps and routing

| step | route |
|------|-------|
| Analyze readiness | Composer read-only snapshot + close plan |
| Prepare/review proposal | OpenClaw Control; stop at 已确认; after 已审核 continue apply chain in this chat |
| Close-apply chain | Same chat: `ndf_close.py plan` + `close-plan --json`; skip integrate when `trunk_src_writes=none`; `ndf_index` + `ndf_graphcheck`; OpenClaw finalize. One POST_ACTION_SYNC at the end |
| ACP integrate | Only if `trunk_src_writes=required`. After POST_DISPATCH_SYNC continue graph/verify/finalize in this chat |
| Verify graph/build/perf/golden | Inside the apply chain; reject skips perf/golden |
| Finalize binder/archive | OpenClaw inside the apply chain after required checks are green |

Every operation carries topic, mode, step, user instruction, `workspace.repo_root` and the
selected topic's `context_plan_sha`. Run context-verify before analysis or work; trust
`context-verify.valid` (content SHA), not raw `slice_manifest_sha` inequality. Human gate
phrases remain human-only.

## POST_ACTION_SYNC

```text
POST_ACTION_SYNC:
1. Do not mark the operation complete merely because it was dispatched.
2. Begin with `action-begin`; after success or failure append `action-finish` with blockers.
3. Run snapshot --update-embedded <managed-canvas> --json (updated=true). Do not pass --probe-runtime.
4. Replace Product / Topics / NDF Control / Agents / Replay. There is no Close tab.
5. Recompute close branches only from actual files/tool results.
6. On failure, display the blocker and leave downstream steps pending.
7. Return the Agent result in Composer; Canvas is not live chat.
8. Require a bound receipt with source generation, context plan, command/input/output SHAs and
   evidence paths.
```

The close-apply chain uses one POST_ACTION_SYNC at the end, not one per mechanical step.

## Evidence versus UI

- Completion comes only from snapshot `control.close` projected on Topics.
- Unknown graph/build/perf/golden state remains pending/unknown.
- Promote, partial and reject are separate branches; reject omits performance/golden.
- `trunk_src_writes=none` marks integrate N/A; do not require an integrate receipt.
- Finalize stays blocked until every required branch step is green.
- Close hops are disabled unless projection freshness is `fresh`.
- `legacy_unbound`, `missing` and unknown receipts remain visible blockers.
