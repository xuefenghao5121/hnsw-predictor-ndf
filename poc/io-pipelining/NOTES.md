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

### ✅ 已完成（代码骨架）

- [x] Step 1–5: pipe_ring_ / L4 readahead / Phase B / L1 prefetch
- [x] 编译通过
- [x] v1 smoke test - **整表作废，不得引用**

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

### ✅ R0 基线（2026-08-01，诚实 cgroup）

**环境**: SIFT1M, 512MB cgroup (systemd-run --user --scope, MemoryMax=512M), 200 queries, k=10, ef=100, REFINE_EF=100

**通用 env**: TWO_STAGE=1, PQ_HYBRID=1, FINE_RERANK=1, CACHE_MB=32, FLAT_VEC_MB=64, PQ_CODES_PATH=output/pqco_sift1m_M32_correct.bin, VEC_BLOCKS_PATH=output/sift1m_vecblocks_64k.bin

**Binary**: build/benchmark_pipe (POC, PIPE_* 全关)

#### 主表：Buffered（FINE_BUFFERED=1）

| 线程 | FINE_PREAD | Recall | QPS (best of 3) | RSS | 对齐 CHR-006 |
|------|-----------|--------|-----------------|-----|-------------|
| 1T | - | 95.75% | **2128.6** | 269MB | ✅ ≥2000 (偏差 +3.2%) |
| 4T | 1 | 95.75% | **6696.5** | 286MB | ✅ ≥5000 (偏差 +33.9%) |

#### 辅表：O_DIRECT（FINE_DIRECT=1）

| 线程 | FINE_PREAD | Recall | QPS (best of 3) | RSS | 对齐 CON-SLA-011 |
|------|-----------|--------|-----------------|-----|-----------------|
| 1T | - | 95.75% | **843.6** | 269MB | ✅ ≥100 (远超锚点 130) |
| 4T | 1 | ❌ 13-20% | ~2908 | 284MB | ⚠ 线程安全 bug，见下 |

**O_DIRECT 4T 问题**: `FINE_PREAD=1 + FINE_DIRECT=1` 时，pread 路径条件 `kFinePread && !kFineDirect` 为 false，回退到共享 `vec_ring_`（非 thread_local），导致 recall 崩。需修复：要么 pread+O_DIRECT（需 aligned buffer），要么 thread_local io_uring。暂不阻塞 R1 进度（主表为 Buffered）。

#### ⚠ v1->R0 排查记录

v1 作废根因（全部已修复）：
1. **PQ_CODE_PATH 少 'S'** -> PQ codes 未加载，粗筛失效
2. **缺 FLAT_VEC_MB=64** -> flat_vec_cache 未启用
3. **缺 PQ_HYBRID=1** -> 粗筛精度下降
4. **FINE_PREAD 无 FINE_BUFFERED** -> buildFineRerank fallback 到 O_DIRECT（4T QPS 仅 ~473）
5. **cgroup 未生效** -> v1 未用 systemd-run

### 待做

- [x] **R0 Buffered** ✅ (2026-08-01)
- [x] **R0 O_DIRECT 辅组** ✅ (1T; 4T 待修线程安全)
- [ ] R1–R4 Buffered 主表；O_DIRECT 辅表
- [ ] 完善 pipe_ring_ page->buf_idx（O_DIRECT 命中）
- [ ] PROFILE_PIPE 统计
- [ ] 修复 O_DIRECT 4T 线程安全（process/bug 提案）

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

### R0 环境配置备忘

```bash
# Buffered 1T
systemd-run --user --scope --quiet -p MemoryMax=512M -p MemorySwapMax=0 -p CPUQuota=100% \
  env TWO_STAGE=1 PQ_HYBRID=1 FINE_RERANK=1 FINE_BUFFERED=1 \
    REFINE_EF=100 CACHE_MB=32 FLAT_VEC_MB=64 \
    PQ_CODES_PATH=output/pqco_sift1m_M32_correct.bin \
    VEC_BLOCKS_PATH=output/sift1m_vecblocks_64k.bin \
  ./build/benchmark_pipe \
    output/sift1m_graph.bin output/sift1m_bfs.bin output/sift1m_blocks_64k.bin \
    output/sift1m_route_64k.bin data/sift_base.fvecs data/sift1m_query200.fvecs \
    data/sift1m_gt200.bin 10 100 200

# Buffered 4T (加 FINE_PREAD=1 NUM_THREADS=4 CPUQuota=400%)
```
