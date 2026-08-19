# Decisions - flat_vec_cache 默认值调优 (DEC-073)

> 条款索引: `DEC-073`

## D-073: flat_vec_cache 默认值 4MB → 64MB {#DEC-073}
<!-- ndf: kind=decision status=stable date=2026-08-05 affects=BEH-024,CON-SLA-014,CON-SLA-016 source=observed -->
<!-- ndf: depends-on=DEC-068,DEC-069,DEC-070,CON-SLA-014 -->

**Context.** perf-gap-4t POC 系统测试发现 flat_vec_cache (FLAT_VEC_MB) 默认值 4MB 过小：
- SIFT1M 512MB cgroup 4T: FVC=160 比 FVC=64 +23.4% QPS (9252→11421)
- SIFT1M 256MB cgroup 4T: FVC=64 是最优 (8838 QPS)
- 4MB 默认无法覆盖足够热向量，FineRerank pread 次数过多

**Decision.** 将默认值从 4MB 调整为 **64MB**:
- 256MB cgroup 下的最优值
- 512MB cgroup 下用户可显式设置 FLAT_VEC_MB=160 获得更佳性能
- 64MB = ~65K 上层向量 (128 dim, 512B/vector)，覆盖 SIFT1M 6.5% 节点

**Consequences.**
- 更高的默认内存占用 (+60MB anon)，在 ≥256MB cgroup 下安全
- QPS 提升显著 (23.4% @512MB cgroup)
- 用户仍可通过环境变量调整

**Non-goals.**
- 不改 WILLNEED/REFINE_EF/PQ M 默认值
- 不改 CON-SLA-014 协议
- 不强制 FLAT_VEC_MB=160 作为默认（256MB cgroup 下不可行）

**Promotes**: perf-gap-4t (D1)
