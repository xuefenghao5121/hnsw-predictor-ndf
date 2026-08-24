# Decisions - BG 页合并 (DEC-075)

> 条款索引: `DEC-075`

## D-075: WILLNEED BG 页合并 {#DEC-075}
<!-- ndf: kind=decision status=stable date=2026-08-06 affects=BEH-027,BEH-028,CON-SLA-018 source=observed -->
<!-- ndf: depends-on=DEC-070,DEC-074,CON-SLA-014 -->

**Context.** l4-cache-mgmt R2 D2 实验发现，WILLNEED_BG 后台线程中合并连续页 fadvise 可减少
syscall 数量约 60%。但效果与 cgroup 预算强相关：

- 256MB 16T: +17.5% QPS (15,891 → 18,675)
- 512MB 16T: -2.9% QPS (30,832 → 29,935) -- 有害

**根因**: 256MB page cache 极度紧张时 syscall 开销占比大；512MB page cache 充裕时
排序开销 > syscall 节省，且更大 readahead 窗口挤占热页。

**Decision.** 将 BG 页合并作为 opt-in 环境变量 `PAGE_MERGE_BG=1` 合入 Trunk。
- 前置条件: `WILLNEED_BG=1`
- 推荐: 仅 256MB cgroup 12T+ 场景
- 不推荐: 512MB cgroup (有害)

**Consequences.**
- 256MB 16T peak: 18,675 QPS (vs BG only 16,873 = +10.7%)
- 新增 BEH-028, CON-SLA-018
- API-013 扩展追加 PAGE_MERGE_BG

**Promotes**: l4-cache-mgmt (partial -- D2 only)
