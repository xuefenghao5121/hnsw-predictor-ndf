# Topic: mmap Read-Only Data to Shift Anon→File Budget

> status: exploring
> track: poc
> created: 2026-08-09
> baseline_trunk_sha: 3e98f3e
> baseline_status: current

## 背景

R0 speculative-prefetch + R0 data-layout 两个 POC 都 rejected。
用户洞察：cgroup budget = anon + file，可以将 read-only 数据结构从 anon 移到 file (mmap)。

## 核心数据

当前 256MB cgroup (DEC-088 实测):
- anon: 229MB (graph + CSR + PQ + cache + FVC)
- file: 27MB (page cache for vecblocks)

可 mmap 的 read-only 数据:
- PQ codes: 30MB
- CSR adjacency: 47MB
- Graph upper vectors: 30MB
- Total: 107MB

## 预期效果

mmap 后:
- anon: ~122MB (-107MB)
- file: ~134MB (+107MB)
- vecblocks coverage: 5.4% → 27% (5x)

## 验证计划

- R0: mmap PQ codes → A/B 金标对比
- R1: extend to CSR + graph upper (if R0 positive)

## 参考条款

- BEH-024 (L4 page cache management)
- DEC-088 (memory budget model)
