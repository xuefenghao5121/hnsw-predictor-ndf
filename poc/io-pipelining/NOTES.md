# POC: I/O Pipelining - 统一多层预取架构

> 提案: `spec/open/proposal-io-pipelining.md` (r3, Buffered 主目标 / [[DEC-062]])
> 关联: [[DEC-060]] 方向 2、[[DEC-062]]、[[BEH-021]]、[[BEH-022]]、[[BEH-023]]、[[API-010]]、[[CON-SLA-013]]
> track: poc | 创建: 2026-08-01 | 修订: 2026-08-01 (r3: Buffered-primary + §7 基线纪律)

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

所有层协作，不分模式分治。pipe_ring_ 两种模式都保留。
**主验证路径 = Buffered**（生产优化主目标）；O_DIRECT = 辅组地板。

## 实现状态

### ✅ 已完成（代码骨架；数字不可信）

- [x] Step 1–5: pipe_ring_ / L4 readahead / Phase B / L1 prefetch
- [x] 编译通过
- [x] Smoke test（见下）— **整表作废，不得引用**

### ⚠ v1 不可信（禁止引用）

| 问题 | 影响 |
|------|------|
| FINE_PREAD 配置错误 | Buffered 路径失真 |
| cgroup 未真正生效 | 非诚实协议 |
| 缺 PQ_HYBRID / FLAT_VEC_MB 等 | 与 SLA 锚点不可比 |
| ~200 query / ~24 QPS smoke | 噪声级，非 R0 |

**MUST NOT** 将下表或任何派生「增量」写入提案证据 / DEC / Trunk SLA。

| 配置 | Recall | QPS | RSS | 状态 |
|------|--------|-----|-----|------|
| baseline / PIPE_* smoke | ~98% | ~24 | ~266MB | **INVALIDATED** |

### 待做（按 §7 基线纪律）

- [ ] **R0 Buffered**：512MB cgroup、正确 env、对齐 [[CHR-006]]（偏差 >10% 先查根因）
- [ ] R0 O_DIRECT 辅组（对齐 [[CON-SLA-011]] ~130）
- [ ] R1–R4 Buffered 主表；O_DIRECT 辅表
- [ ] 完善 pipe_ring_ page→buf_idx（O_DIRECT 命中）
- [ ] PROFILE_PIPE 统计

## §7 POC 基线纪律（强制）

每次优化前 MUST：

1. 在与目标一致的配置（cgroup、线程、数据集、**Buffered 优先**）下先跑基线
2. 基线写入本 NOTES 作为 **R0** 锚点
3. 后续轮次只与 R0 对比，不得跳过基线
4. 若 R0 与 [[CHR-006]] / [[CON-SLA-011]] 偏差 >10%，先定位根因再继续

## NOTES

- pipe_ring_ 是 `static thread_local`，多线程安全
- 与 `SPEC_PREFETCH=1` 可共存（不同层）
- 不改 I/O 粒度（避免重蹈 [[DEC-061]]）
- Buffered 下 pipe_ring_ 核心价值 = **主动填 L4**（[[BEH-021]] / [[DEC-062]]）
- 本目录为探索轨；**禁止**把实验默认合入 `src/`（[[BEH-018]]）
