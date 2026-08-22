# POC: I/O Pipelining - 统一多层预取架构

> status: rejected
> close: reject | 2026-08-04 | [[DEC-071]]（WILLNEED 取代 pipe_ring_）
> 提案: `spec/open/proposal-io-pipelining.md` (r3)
> 关联: [[DEC-060]]、[[DEC-062]]、[[DEC-063]]、[[DEC-064]]、[[BEH-021]]…[[BEH-023]]、[[API-010]]、[[CON-SLA-013]]
> 装订器: `ndf/TOPIC.md`（[[BEH-025]]）；修正案见 `proposal-io-behavior-correction.md`
> track: poc | 创建: 2026-08-01 | 修订: 2026-08-02（同步 DEC-063/064 卫生）

## 架构

```
Disk (NVMe)
    ↓ io_uring (O_DIRECT or Buffered)
L5: pipe_ring_ (~800KB, 单 query, thread_local)
    ↓
L4: Page Cache (cgroup_limit - RSS, ~240-390MB, 跨 query)
    ↓
L1/L2/L3: CPU Cache (~30MB L3, 单次计算)
```

**主验证路径 = Buffered**；O_DIRECT = 辅组。pipe 默认关闭；**未 promote**（[[DEC-064]]）。

## 实现状态

### ✅ 已完成

- [x] pipe_ring_ / L4 / L1 骨架；`pipe_piped_pages_` / `pipe_page_bufidx_` → thread_local
- [x] SIFT1M R0–R4 → **负结果** [[DEC-063]]
- [x] DEEP10M pre-memopt 相对对比（Buffered+EVICT）→ +162.6% @1T（**非** CON-SLA-013 O_DIRECT 达标）
- [x] 副产品内存优化 → promote [[DEC-064]]（Trunk）；post-memopt 后 pipe **无收益**

### ⚠ v1 不可信（禁止引用）

| 问题 | 影响 |
|------|------|
| FINE_PREAD / cgroup / 缺 FLAT_VEC 等 | ~24 QPS smoke **INVALIDATED** |

### ✅ R0 基线（SIFT1M，诚实 cgroup）

详见历史表：Buffered 1T=2128.6 / 4T=6696.5（对齐 [[CHR-006]]）。
O_DIRECT 1T=843.6（≥ CON-SLA-011）；O_DIRECT 4T recall 崩（FINE_PREAD+FINE_DIRECT bug，仍开放）。

### 待做

- [x] R0–R4 SIFT1M
- [x] DEEP10M pre-memopt 1T 相对对比（口径见 [[DEC-063]]）
- [x] thread_local 4T 竞争修复
- [ ] Post-memopt + thread_local 后 DEEP10M 4T（`proposal-4t-scaling-investigation.md`）
- [ ] O_DIRECT 4T（FINE_PREAD+FINE_DIRECT）线程安全
- [ ] 100M / 明确 I/O-bound 下再评估 pipe promote 或 deprecated
- [ ] PROFILE_PIPE 统计

## §7 POC 基线纪律（强制）

1. 目标一致配置下先跑 R0（Buffered 优先）
2. 写入 NOTES；后续只与 R0 比
3. 相对对比若非 Honest/O_DIRECT，MUST 在 DEC/NOTES 标明协议（同 [[DEC-063]]）
4. R0 与 [[CHR-006]] / [[CON-SLA-011]] 偏差 >10% → 先查根因

## NOTES

- pipe 探索轨；禁止默认合入 `src/`（[[BEH-018]]）
- 不改 I/O 粒度（避 [[DEC-061]]）
- post-[[DEC-064]]：DEEP10M 上 page cache 预算充足时 pipe 为纯开销

## §8 I/O Behavior Correction 重测 (2026-08-04, CON-SLA-014)

### 前置变更
- 同步 Trunk flat_vec_cache check (DEC-068) + WILLNEED (DEC-070) + L4_EVICT_META 到 POC 代码
- 修复 Makefile 路径（从 poc/ 目录运行）

### DEEP10M 结果

| 配置 | cgroup | PIPE_FINE | QPS | Recall | RSS | refault | majfault | pipe_hits |
|------|--------|-----------|-----|--------|-----|---------|----------|-----------|
| R0-base | 2GB | 0 | 563 | 95.05% | 1155MB | 275 | 69295 | 0 |
| R1-pipe | 2GB | 1 | 558 | 95.05% | 1145MB | 267 | 69527 | 255 |
| R0-base | 3GB | 0 | 563 | 95.05% | 1571MB | 48 | 6 | 0 |
| R1-pipe | 3GB | 1 | 553 | 95.05% | 1562MB | 64 | 6 | 255 |

### 判定

**pipe_ring_ 在 CON-SLA-014 下无收益。**

- 2GB: R1 vs R0 = -0.9%（噪声），有 I/O 舞台 (majfault=69K) 但 pipe 无贡献
- 3GB: R1 vs R0 = -1.8%（pipe 开销），无 I/O 舞台 (majfault=6)
- pipe_hits=255 证明机械工作正常，但对 QPS 无影响

### 根因

WILLNEED (DEC-070) 已在 pread 之前启动异步 readahead，实现了 I/O 与 CPU 并行。
pipe_ring_ 的预取与 WILLNEED 的预取重叠——两者都在 Phase A 候选收集后、Phase B pread 前
触发。WILLNEED 的 promote 使 pipe_ring_ 失去了独立价值。

### 下一步建议

按 [[BEH-020]] 负结果闭环：
1. 产品 DEC 记录根因（WILLNEED 取代 pipe）
2. BEH-021/022/023 deprecated
3. TOPIC status = rejected
