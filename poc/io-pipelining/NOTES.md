# POC: I/O Pipelining - 统一多层预取架构

> 提案: `spec/open/proposal-io-pipelining.md` (r3)
> 关联: [[DEC-060]]、[[DEC-062]]、[[DEC-063]]、[[DEC-064]]、[[BEH-021]]…[[BEH-023]]、[[API-010]]、[[CON-SLA-013]]
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
