# Topic: mmap Read-Only Data to Shift Anon->File Budget

> status: exploring
> track: poc
> created: 2026-08-09
> baseline_trunk_sha: 434c6f5
> baseline_status: current

## 背景

R0 speculative-prefetch + R0 data-layout 两个 POC 都 rejected。
用户洞察：cgroup budget = anon + file，可以将 read-only 数据结构从 anon 移到 file (mmap)。

## 审计修正 (2026-08-10)

1. Upper vectors 在 kUpperPQ=1（默认）下已释放（DEC-034），稳态 0MB -> 排除出 mmap 范围
2. PQ codes M_pq=32（非 M_graph=24），实际 32MB
3. CSR 为 Delta+Varint 压缩存储（DEC-064），实际大小需 R0 实测
4. baseline_trunk_sha 修正为 434c6f5（与金标一致）
5. 预期效果从 5x 下调为 ~4x

## 核心数据 (修正后)

当前 256MB cgroup (Config C M=24, 稳态):
- anon: ~197MB (PQ 32MB + CSR ~40-60MB + FVC 64MB + BlockCache 64MB + misc 5MB)
- file: 27MB (page cache for vecblocks)

可 mmap 的 read-only 数据:
- PQ codes: 32MB (M_pq=32, file: pqco_sift1m_M32_correct.bin)
- CSR adjacency: ~40-60MB (Delta+Varint 压缩, 需实测)
- PQ codebook: 0.1MB (可忽略)
- Total: ~72-92MB

## 预期效果 (修正后)

mmap 后:
- anon: ~105-125MB (-72~92MB)
- file: ~99-119MB (+72~92MB)
- vecblocks coverage: 5.4% -> ~19-23% (~4x)

## 验证计划

- 测试脚本: 复用 run_strict.sh 金标模式 (cgroup_utils.sh 完整流程)
  - cg_init -> cg_create -> cg_set_limit -> cg_drop_caches -> cg_add_proc
  - cg_stats: anon/file/peak/violations/refault/majfault
- 测试标准: **CON-SLA-020 sustained**（金标）
  - CON-SLA-019 禁预热
  - CON-SLA-014 严格 cgroup 隔离
  - 15轮x1000q, seed=42
  - 报告聚合 QPS + 稳态 QPS + cgroup 完整统计
- 基线配置: **Config C (DEC-087 Pareto 最优, M=24 EF=60)**
  - 金标基线 (256MB 1T): agg 1,450 / steady 1,702 / recall 96.60%
- R0: mmap PQ codes -> A/B sustained 金标对比
- R1: extend to CSR (if R0 positive)

## 参考条款

- BEH-024 (L4 page cache management)
- BEH-027 (WILLNEED BG)
- DEC-034 (Upper vectors PQ 释放)
- DEC-064 (CSR Delta+Varint 压缩)
- DEC-088 (memory budget model)
- CON-SLA-019 (禁预热)
- CON-SLA-020 (sustained query measurement)
