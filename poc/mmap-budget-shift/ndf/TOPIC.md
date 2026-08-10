# Topic: mmap Read-Only Data to Shift Anon->File Budget

> status: exploring (R0 PQ codes rejected, R1 CSR in progress)
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
3. CSR 为 Delta+Varint 压缩存储（DEC-064），57MB (54MB compact + 3MB offsets)
4. baseline_trunk_sha 修正为 434c6f5（与金标一致）
5. 预期效果从 5x 下调为 ~4x

## 核心数据

当前 256MB cgroup (Config C M=24, 稳态):
- anon: ~197MB (PQ 30MB + CSR 57MB + FVC 64MB + BlockCache 64MB + misc 5MB)
- file: 27MB (page cache for vecblocks)

可 mmap 的 read-only 数据:
- PQ codes: 30MB → R0 REJECTED (page cache thrashing)
- CSR adjacency: 57MB → R1 (in progress)

## R0 结果: PQ codes mmap REJECTED

脚本: scripts/run_sustained.sh (CON-SLA-020 金标)
配置: Config C (M=24 EF=60), 256MB 1T, 15轮×1000q, seed=42

| | A (vector) | B (mmap) | Delta |
|--|:---:|:---:|:---:|
| agg QPS | 1,431.6 | 277.0 | -80.6% |
| steady QPS | 1,662.7 | 267.4 | -83.9% |
| recall | 96.60% | 96.60% | 0 |

根因: PQ codes (30MB file-backed) 与 vecblocks 在 page cache 中 thrashing。
Ramp-up 仅 5%，page fault 贯穿全部 15 轮。

## R1 计划: CSR mmap

CSR 与 PQ codes 访问模式差异:
- CSR: BFS 重排后有空间局部性, varint 压缩 ~2B/edge
- PQ codes: 纯随机, 无局部性
- 但 CSR 57MB > PQ 30MB, page cache 争夺面更大

验证: A (vector CSR) vs B (mmap CSR), 金标 scripts/run_sustained.sh
唯一差异: CSR_MMAP_PATH 环境变量

## 验证计划

- 测试脚本: **scripts/run_sustained.sh** (正式金标 CON-SLA-020 载体)
  - source scripts/cgroup_utils.sh (API-016 工具库)
  - cg_init -> cg_create -> cg_set_limit -> cg_drop_caches -> cg_add_proc
  - cg_stats_summary + cg_check_violations
  - A/B 唯一差异: CSR_MMAP_PATH
- 测试标准: CON-SLA-020 sustained + CON-SLA-019 禁预热 + CON-SLA-014 严格 cgroup
- 基线配置: Config C (DEC-087: M=24 EF=60)
  - 金标基线 (256MB 1T): agg 1,450 / steady 1,702 / recall 96.60%

## 参考条款

- BEH-024 (L4 page cache management)
- BEH-027 (WILLNEED BG)
- DEC-034 (Upper vectors PQ 释放)
- DEC-064 (CSR Delta+Varint 压缩)
- DEC-088 (memory budget model)
- CON-SLA-014 / CON-SLA-019 / CON-SLA-020
