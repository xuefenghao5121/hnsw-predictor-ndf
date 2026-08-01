# Decisions - I/O Pipelining POC (DEC-063)

> 条款索引: `DEC-063`
> 关联: `DEC-060`（方向 2）、`DEC-062`、`BEH-021`、`BEH-022`、`BEH-023`、`CON-SLA-013`、`CON-POC-001`

## D-063: SIFT1M 规模 I/O Pipelining 负结果 - 转向 DEEP10M 验证 {#DEC-063}
<!-- ndf: kind=decision date=2026-08-01 affects=DEC-060,BEH-021,BEH-022,BEH-023,CON-SLA-013 source=observed -->
<!-- ndf: depends-on=DEC-062,CON-HONEST-002,CON-POC-001 -->

**Context.** DEC-060 方向 2（I/O Pipelining）在 `poc/io-pipelining/` 中实现并验证。
本决策记录 SIFT1M 规模下的负结果及根因分析。

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

**Decision.**

1. **SIFT1M 规模下 I/O Pipelining 证伪**：pipe_ring_ / L4 readahead / L1 prefetch 均无收益
2. **根因 = 数据集太小**：496MB vecblocks 的热集完全装入 page cache + flat_vec_cache，I/O 非瓶颈
3. **转向 DEEP10M 验证**：3.7GB vecblocks / 2GB cgroup / page cache 覆盖率仅 10%，I/O 是真正瓶颈
4. **BEH-021/022/023 + CON-SLA-013 保持 draft**：不 deprecated，待 DEEP10M 验证后决定
5. **O_DIRECT 4T 线程安全 bug 记录**：`FINE_PREAD=1 + FINE_DIRECT=1` 条件冲突，需修复

**DEEP10M 验证目标**（对齐 CON-SLA-013 辅表）：

| 指标 | O_DIRECT 基线 | POC 目标 | 说明 |
|------|-------------|----------|------|
| DEEP10M 4T QPS | 169 | ≥ 220 | Phase A ~7ms 可隐藏大量 I/O |

**Alternatives rejected.**
- 直接 deprecated BEH-021/022/023：SIFT1M 不是有效验证场景，负结果不可推广
- 继续在 SIFT1M 调参：热集 < cache 预算的根本矛盾无法通过参数调整解决
- 用 EVICT_PAGE_CACHE=1 模拟冷态：flat_vec_cache 吸收热点，无法制造真正冷 I/O

> rationale: SIFT1M（1M/496MB）的 page cache 预算足以覆盖热集，I/O pipelining 的
> 价值需要在 page cache 覆盖率 < 15% 的场景下验证。DEEP10M（10M/3.7GB）的
> page cache 覆盖率仅 ~10%，Phase A 持续 ~7ms，是 I/O 重叠的真正战场。
> 负结果仅限于 SIFT1M 规模，不构成对 pipelining 方向本身的否定。
