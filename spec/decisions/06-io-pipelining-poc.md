# Decisions - I/O Pipelining POC (DEC-063)

> 条款索引: `DEC-063`
> 关联: `DEC-060`（方向 2）、`DEC-062`、`DEC-064`、`BEH-021`、`BEH-022`、`BEH-023`、`CON-SLA-013`、`CON-POC-001`

## D-063: I/O Pipelining POC - SIFT1M 负结果 + DEEP10M 相对正结果 {#DEC-063}
<!-- ndf: kind=decision date=2026-08-01 affects=DEC-060,BEH-021,BEH-022,BEH-023,CON-SLA-013 source=observed -->
<!-- ndf: depends-on=DEC-062,CON-HONEST-002,CON-POC-001 -->
<!-- ndf: amended-by=DEC-064 -->

> **Amendment ([[DEC-064]], 2026-08-02):** DEEP10M 上 pipe_ring_ +162.6% 的 1T 数字为
> **pre-memory-optimization** 相对对比（Buffered + `EVICT_PAGE_CACHE=1`）。
> 内存优化 promote 后同协议下 R1≈R0，pipe 无收益。SIFT1M 负结果仍然有效。
> **MUST NOT** 将下文 DEEP10M 数字当作 [[CON-SLA-013]] O_DIRECT 辅表「已达成」。

**Context.** DEC-060 方向 2（I/O Pipelining）在 `poc/io-pipelining/` 中实现并验证。
本决策记录 SIFT1M 规模下的负结果、DEEP10M 规模下的正结果，以及 cgroup page cache 审计发现。

### 实现概要

- **L5 pipe_ring_**（`PIPE_FINE=1`）：thread_local io_uring，Phase A 搜索时异步预取候选向量 4KB 页
- **L4 readahead**（`PIPE_L4=1`）：pipe_ring_ buffer 耗尽时 fallback 到 `readahead()` 系统调用
- **L1 CPU cache prefetch**（`PIPE_L1=1`）：`_mm_prefetch` 预取即将计算的向量到 L1

### 实测结果（SIFT1M, 512MB cgroup, 1T/4T, drop_caches 冷启动）

#### R0-R4 对比（热态，cat 预热，page cache 非诚实）

| 轮次 | 配置 | 1T QPS | 4T QPS | vs R0 |
|------|------|--------|--------|-------|
| R0 | baseline | 2128.6 | 6696.5 | - |
| R1 | +PIPE_FINE | 2103.3 | 6905.0 | -1.2% / +3.1% |
| R2 | +FINE+L1 | 2108.5 | 6566.9 | -0.9% / -1.9% |
| R3 | +FINE+L4 | 2018.4 | 6326.1 | -5.2% / -5.5% |
| R4 | 全开 | 2021.6 | 6181.7 | -5.0% / -7.7% |

#### drop_caches 冷启动验证（1T, 6 轮交替）

| 轮次 | R0 QPS | R1 QPS |
|------|--------|--------|
| 1 | 2017.2 | 2076.4 |
| 2 | 2098.4 | 2038.6 |
| 3 | 2115.8 | 2069.8 |
| 4 | 2110.7 | 2092.7 |
| **均值** | **2085.5** | **2069.4** |

**结论：R1 vs R0 = -0.8%，无统计显著收益。**

### cgroup page cache 审计

| 条件 | QPS | memory.peak | max events | 说明 |
|------|-----|-------------|-----------|------|
| cat 预热（父 cgroup） | 2128 | 408MB | 0 | page cache 未计入子 cgroup，512MB 限制未生效 |
| drop_caches 冷启动 | 2085 | 512MB | ~2000 | cgroup 真正生效，内核回收 page cache ~2000 次 |
| fadvise 驱逐 | 2117 | 512MB | ~1979 | 同 drop_caches，cgroup 生效 |

**重要发现**：`cat` 预热在父 cgroup（用户会话）执行，page cache 算在父 cgroup 账上。
子 cgroup 访问这些页时不重新记账，512MB 限制只管匿名内存。但实测 QPS 无差异——
benchmark 内部 warmup（200 query 跑一遍）足以加载热集到 cgroup 内 page cache。

### 根因分析

SIFT1M 规模下 I/O 不是瓶颈：

```
vecblocks:          496MB
page cache 预算:     243MB (512MB - 269MB RSS)  -> 覆盖 48%
flat_vec_cache:      64MB (匿名内存)             -> 覆盖 13% (65K 向量)
热集 (200 query):    ~100MB                       -> 完全在 cache 内
```

1. **热集 < page cache 预算**：200 条 query 访问的向量页 ~100MB，完全装进 243MB 预算
2. **flat_vec_cache 吸收热点**：64MB 匿名内存缓存 65K 向量，EVICT_PAGE_CACHE=1 也无法制造冷态
3. **pipe_ring_ 开销 > 收益**：io_uring 提交/reap 开销在 page cache hit 场景下是纯开销
4. **readahead() 有害**：对已缓存页调用 readahead() 强制内核检查/驱逐，R3/R4 反而更慢
5. **4T pipe_piped_pages_ 竞争**：成员变量非 thread_local，增加方差（不致命）

### v1 作废根因（全部已修复）

POC v1 smoke test（~24 QPS）作废的 5 个根因：
1. `PQ_CODE_PATH` 少 'S' → PQ codes 未加载
2. 缺 `FLAT_VEC_MB=64` → flat_vec_cache 未启用
3. 缺 `PQ_HYBRID=1` → 粗筛精度下降
4. `FINE_PREAD=1` 未搭配 `FINE_BUFFERED=1` → buildFineRerank fallback 到 O_DIRECT
5. cgroup 未用 `systemd-run` → 未真正生效

**Decision（SIFT1M 阶段，2026-08-01）。**

1. **SIFT1M 规模下 I/O Pipelining 证伪**：pipe_ring_ / L4 readahead / L1 prefetch 均无收益
2. **根因 = 数据集太小**：496MB vecblocks 的热集完全装入 page cache + flat_vec_cache，I/O 非瓶颈
3. **转向 DEEP10M 验证**：3.7GB vecblocks，page cache 覆盖率低，I/O 可为瓶颈
4. **BEH-021/022/023 + CON-SLA-013 保持 draft**：不 deprecated
5. **O_DIRECT 4T 线程安全 bug 记录**：`FINE_PREAD=1 + FINE_DIRECT=1` 条件冲突，需修复

**探索目标（非 CON-SLA-013 辅表达标声明）**：在 I/O-bound 协议下验证 pipe 相对 R0 是否有正增益。
[[CON-SLA-013]] O_DIRECT 辅表（DEEP10M 4T ≥220）仍为 draft 目标；**本决策 DEEP10M 实测协议
为 Buffered + EVICT，不得与 O_DIRECT 辅表混报为「已达成」**（[[CON-POC-001]]）。

**Alternatives rejected.**
- 直接 deprecated BEH-021/022/023：SIFT1M 不是有效推广场景
- 继续在 SIFT1M 调参：热集 < cache 预算的根本矛盾无法靠参数解决
- 用 EVICT_PAGE_CACHE=1 模拟冷态（SIFT1M）：flat_vec_cache 吸收热点

### DEEP10M 相对正结果（2026-08-02，pre-memopt）

> **协议口径**：`FINE_BUFFERED=1` + `EVICT_PAGE_CACHE=1` + 10000q —— **相对对比实验**。
> 非 [[CON-HONEST-002]] O_DIRECT 地板；非 [[CON-SLA-013]] O_DIRECT 辅表验收。

**环境**: DEEP10M (10M/96dim), 5GB cgroup, 10000 queries, k=10, ef=300, REFINE_EF=300
**配置**: M=32 PQ (dsub=3), FINE_BUFFERED=1, FINE_PREAD=1, EVICT_PAGE_CACHE=1, CACHE_MB=64, FLAT_VEC_MB=64
**Binary**: build/benchmark_pipe (POC)

#### 1T 结果（3 轮取均值）

| 轮次 | R0 QPS | R1 QPS (PIPE_FINE=1) | R1 vs R0 | Recall |
|------|--------|---------------------|----------|--------|
| Round 1 | 106.8 | 279.0 | +161.5% | 94.85% |
| Round 2 | 106.6 | 280.4 | +163.0% | 94.85% |
| Round 3 | 105.8 | 278.6 | +163.3% | 94.85% |
| **均值** | **106.4** | **279.3** | **+162.6%** | 94.85% |

**关键发现**: pipe_ring_ 几乎完全消除了该协议下的冷 I/O 惩罚。
- R0 热态 (200q, 无 EVICT): 283.9 QPS
- R0 冷态 (10000q, EVICT): 106.4 QPS (I/O 惩罚 2.7x)
- R1 冷态 (10000q, EVICT+PIPE): 279.3 QPS (vs 热态仅差 1.6%)

pipe_hits=255/query，Phase A 预取的页在 Phase B 命中，I/O 延迟被 Phase A 计算完全隐藏。

#### 4T 结果（thread_local 修复前）

| 配置 | 4T QPS | vs 1T | 说明 |
|------|--------|-------|------|
| R0 4T | 180.3 | 1.69x | scaling 不理想 |
| R1 4T | 249.4 | 0.89x ⚠ | 比 1T 还慢 |
| R1 vs R0 | +38.3% | - | 远低于 1T 的 +162.6% |

**4T 退化根因（已修复）**: `pipe_piped_pages_` / `pipe_page_bufidx_` 曾为成员变量；
commit `7742330` 已改为 `thread_local`。修复后完整 4T 重测见 `proposal-4t-scaling-investigation.md`。

### cgroup page cache 审计发现

| 条件 | QPS | memory.peak | max events | 说明 |
|------|-----|-------------|-----------|------|
| cat 预热（父 cgroup） | 2128 | 408MB | 0 | page cache 未计入子 cgroup |
| drop_caches 冷启动 | 2085 | 512MB | ~2000 | cgroup 真正生效 |

`cat` 预热在父 cgroup 执行，page cache 算在父 cgroup 账上。子 cgroup 访问时不重新记账。
但实测 QPS 无差异（热集 < page cache 预算）。

### DEEP10M 环境修复记录

1. **GT 文件错误**: `deep10m_gt_k10_fresh.bin` 是自引用 GT → 改用 `data/deep10m_gt_k10.bin`
2. **PQ M=8 太粗**: recall 52.6% → M=32 (dsub=3) recall 95.05%
3. **路由文件错误**: 改用 `deep10m_route_64k.bin`
4. **FINE_PREAD 必须开**: 不开时走 io_uring 路径，recall 88.4%（可能有 bug）
5. **cgroup（pre-memopt）需 5GB**: RSS 2422MB + 临时内存；post-memopt 见 [[DEC-064]]（可 3GB）

**Decision（终态，含 [[DEC-064]] 修正）。**

1. **SIFT1M：I/O Pipelining 证伪**（稳定结论）
2. **DEEP10M pre-memopt：相对对比正结果**（+162.6% @ Buffered+EVICT 1T）——**不是**
   [[CON-SLA-013]] O_DIRECT 辅表达标，也**不是** promote pipe 的充分证据
3. **DEEP10M post-memopt：pipe 无收益**（[[DEC-064]]）；BEH-021/022/023 + CON-SLA-013 **保持 draft**
4. **thread_local 竞争 bug：已修**；post-fix 4T 重测仍开放（`proposal-4t-scaling-investigation.md`）
5. **O_DIRECT 4T（FINE_PREAD+FINE_DIRECT）线程安全：仍开放**

**后续 POC 步骤:**
- [x] 修复 pipe_piped_pages_ / pipe_page_bufidx_ 为 thread_local
- [ ] 修复 O_DIRECT 4T 线程安全（FINE_PREAD+FINE_DIRECT）
- [ ] Post-memopt + thread_local 后 DEEP10M 4T 重测（见 4T 提案）
- [ ] 100M 或明确 I/O-bound 协议下再评估是否 promote pipe / deprecated

> rationale: SIFT1M 热集可被 page cache 覆盖；DEEP10M+EVICT 曾暴露 pipe 隐藏延迟的价值，
> 但内存优化抬高 page cache 预算后该收益消失（[[DEC-064]]）。探索轨允许主目标暂缓、
> 副产品晋升。口径上相对对比不得冒充 O_DIRECT 辅表或 Trunk SLA（[[CON-POC-001]]）。
