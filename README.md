# DiskHNSW - 内存受限环境下的磁盘向量搜索

> 在 cgroup 内存限额下，用磁盘驻留向量做接近全内存 HNSW 的召回（≥95%）。
>
> **Sustained（官方 10K query 池, N=1000, R=15, 禁预热）:**
>
> | 配置 | 聚合 QPS | 稳态 QPS | Recall | RSS |
> |------|---------|---------|--------|-----|
> | SIFT1M 512MB 16T | 4,475 | 6,831 | 96.00% | ~242MB |
> | SIFT1M 512MB 16T +ADAPTIVE | 5,651 | 9,862 | 95.80% | ~242MB |
> | SIFT1M 256MB 16T | 2,092 | 2,413 | 96.00% | ~223MB |
> | DEEP10M 2GB 12T | - | - | 95.15% | 1,612MB |
>
> **对照 hnswlib unlimited (16T):** 42,947 QPS / 98.25% recall / 763MB RSS
>
> **真实定位:** 能在内存预算不足时工作（hnswlib 在 DEEP10M 直接 OOM），
> 绝对内存占用低（256MB vs 763MB = 33%），吞吐为 trade-off。
>
> **平台:** x86_64 (AVX2) ✅ | ARMv9 AArch64 (NEON) ✅
>
> ⚠️ 早期文档中的 30,332 / 18,675 QPS 为 **cache-warmed 口径**（200q + query 预热），
> 高估 1.73–7.60×，仅作回归护栏。详见 [[DEC-084]]、[[CON-SLA-019]]。

## 项目背景

传统 HNSW 向量搜索需要将全部向量加载到内存。对于 1M 条 128 维 SIFT 向量，hnswlib 需 726MB RSS；10M 条 96 维 DEEP 向量需 ~7GB。在容器化、边缘计算等内存受限场景下不可行。

DiskHNSW 的核心思路：

1. **图结构常驻内存** - 上层节点向量 + L0 邻接表 CSR 压缩
2. **向量数据存磁盘** - BFS 重排后分块，利用空间局部性
3. **PQ 粗筛** - Product Quantization 压缩向量常驻内存，零 I/O 近似距离搜索
4. **精确精排 (Fine Rerank)** - 对粗筛候选集按 4KB 页粒度读真实向量做精确 L2
5. **I/O 优化** - WILLNEED_BG 无锁后台预取 + flat_vec_cache 热向量缓存 + PAGE_MERGE_BG 连续页合并
6. **跨架构** - SIMD 抽象层 (simd.h) 统一 x86 AVX2 / ARM NEON, 编译时自动选择

---

## 快速开始

### 编译

```bash
# 依赖: Linux 5.1+ (io_uring), g++ C++17, Python 3 + faiss
# 支持: x86_64 (AVX2) / ARMv9 AArch64 (NEON)
make all   # 自动检测架构, pipeline 工具 + benchmark + 测试
```

### 一键准备数据（SIFT1M）

```bash
# 下载 SIFT1M base/query 到 data/
bash scripts/build_pipeline.sh data/sift_base.fvecs sift1m 32
# 产出: output/sift1m_{index,graph,bfs,blocks_64k,route_64k,vecblocks_64k}.bin
#       output/pqco_sift1m_M32_correct.bin
```

### 运行 Sustained Benchmark（推荐）

```bash
# Sustained 基准（官方 10K query 池, 多轮随机采样, 禁预热）
# 这是对外吞吐声明的权威口径 (CON-SLA-020)
sync; echo 3 | sudo tee /proc/sys/vm/drop_caches
sudo mkdir -p /sys/fs/cgroup/hnsw_test
echo $((512 * 1024 * 1024)) | sudo tee /sys/fs/cgroup/hnsw_test/memory.max
echo $$ | sudo tee /sys/fs/cgroup/hnsw_test/cgroup.procs

TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1 \
L4_WILLNEED=1 WILLNEED_BG=1 VL_POOL_THREADS=14 \
VEC_BLOCKS_PATH=output/sift1m_vecblocks_64k.bin \
PQ_CODES_PATH=output/pqco_sift1m_M32_correct.bin \
CACHE_MB=64 FLAT_VEC_MB=160 REFINE_EF=100 \
./build/benchmark_sustained \
    output/sift1m_graph.bin output/sift1m_bfs.bin \
    output/sift1m_blocks_64k.bin output/sift1m_route_64k.bin \
    data/sift_base.fvecs data/sift_query_official10k.fvecs data/sift_groundtruth_official.ivecs \
    10 100 1000 --rounds 15 --seed 42
```

### 运行 Cache-warmed Benchmark（回归护栏）

```bash
# 200q 标准 benchmark (cache-warmed, 仅作回归基线)
# ⚠️ 数字高估 1.73-7.60x, 不可对外引用为商用吞吐
TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1 \
L4_WILLNEED=1 WILLNEED_BG=1 VL_POOL_THREADS=14 \
VEC_BLOCKS_PATH=output/sift1m_vecblocks_64k.bin \
PQ_CODES_PATH=output/pqco_sift1m_M32_correct.bin \
CACHE_MB=64 FLAT_VEC_MB=160 REFINE_EF=100 \
./build/benchmark_diskhnsw \
    output/sift1m_graph.bin output/sift1m_bfs.bin \
    output/sift1m_blocks_64k.bin output/sift1m_route_64k.bin \
    data/sift_base.fvecs data/sift1m_query200.fvecs data/sift1m_gt200.bin \
    10 100 200
```

### 严格 cgroup 隔离测试

```bash
sync; echo 3 | sudo tee /proc/sys/vm/drop_caches
sudo mkdir -p /sys/fs/cgroup/hnsw_test
echo $((512 * 1024 * 1024)) | sudo tee /sys/fs/cgroup/hnsw_test/memory.max
echo $$ | sudo tee /sys/fs/cgroup/hnsw_test/cgroup.procs

# 运行后检查内存
cat /sys/fs/cgroup/hnsw_test/memory.peak
grep -E "^(anon|file|workingset_refault_file|pgmajfault)" /sys/fs/cgroup/hnsw_test/memory.stat
```

---

## 数据准备 Pipeline（7 步）

> **三条铁律**：① 一套数据从头到尾 ② graph 与 blocks 同批生成 ③ PQ 的 M 匹配维度

| 步骤 | 命令 | 产出 |
|------|------|------|
| 1. 建图 | `./build/build_index data/sift_base.fvecs output/sift1m_graph.bin` | 分层 Vamana 图结构 |
| 2. 提取图 | （已合并入建图——build_index 直接产出 GraphStructure） | — |
| 3. BFS 重排 | `./build/bfs_reorder output/sift1m_graph.bin output/sift1m_bfs.bin` | old↔new 映射 |
| 4. Vec-Only 块 | `./build/write_blocks_veconly output/sift1m_graph.bin output/sift1m_bfs.bin output/sift1m_vecblocks_64k.bin 65536` | 向量块 + route |
| 5. 旧格式块 | `./build/write_blocks ... && ./build/gen_route ...` | BlockCache 用 |
| 6. PQ 编码 | `python3 scripts/train_pq.py data/sift_base.fvecs output/pqco_sift1m_M32_correct.bin 32` | PQ codes |
| 7. Ground Truth | `python3 scripts/gen_gt.py data/sift_base.fvecs data/sift1m_query200.fvecs data/sift1m_gt200.bin 10` | 真实 top-K |

> 或直接 `bash scripts/build_pipeline.sh data/sift_base.fvecs sift1m 32`

---

## 性能数据

### Sustained 基准（权威口径）

> 测量协议: 官方 SIFT 10K query 池, N=1000, R=15, seed=42, 禁预热 (CON-SLA-019/020)
> 对照: hnswlib unlimited memory, 同官方 query + 同官方 GT

**SIFT1M (128维, 100万向量) - Sustained QPS:**

| 配置 | 模式 | 聚合 QPS | 稳态 QPS | Recall |
|------|------|---------|---------|--------|
| 512MB 1T | BASE | 1,493 | 1,698 | 96.00% |
| 512MB 1T | ADAPTIVE | 1,654 | 1,943 | 95.80% |
| 512MB 4T | BASE | 3,920 | 5,355 | 96.00% |
| 512MB 4T | ADAPTIVE | 4,328 | 6,176 | 95.80% |
| 512MB 8T | BASE | 4,525 | 6,885 | 96.00% |
| 512MB 8T | ADAPTIVE | 5,352 | 8,466 | 95.80% |
| 512MB 16T | BASE | 4,475 | 6,831 | 96.00% |
| 512MB 16T | ADAPTIVE | 5,651 | 9,862 | 95.80% |
| 256MB 1T | BASE | 1,090 | 1,160 | 96.00% |
| 256MB 4T | BASE | 2,201 | 2,518 | 96.00% |
| 256MB 4T | ADAPTIVE | 2,828 | 3,329 | 95.81% |
| 256MB 8T | BASE | 2,185 | 2,551 | 96.00% |
| 256MB 8T | ADAPTIVE | 2,920 | 3,536 | 95.81% |
| 256MB 16T | BASE | 2,092 | 2,413 | 96.00% |
| 256MB 16T | ADAPTIVE | 2,777 | 3,416 | 95.81% |

> ADAPTIVE = `ADAPTIVE_EF=1`（PQ 距离间隙启发式候选数，sustained 下 +12.5~31.4%）
> GBDT (`LEARNED_EF=1`) 在 sustained 下 +12.3~47.4% (重训练复活, BEH-034 must)

**vs hnswlib unlimited (sustained):**

| 配置 | 稳态 QPS | 内存 | vs hnswlib QPS | QPS/MB | vs hnswlib QPS/MB |
|------|---------|------|---------------|--------|------------------|
| hnswlib 16T | 42,947 | 763MB | 100% | 56.3 | 1.0× |
| DiskHNSW 512MB 16T | 6,694 | 512MB | 15.6% | 13.1 | 0.23× |
| DiskHNSW 512MB 16T +ADAPTIVE | 9,560 | 512MB | 22.2% | 18.7 | 0.33× |
| DiskHNSW 256MB 16T | 2,456 | 256MB | 5.7% | 9.6 | 0.17× |

**真实定位（trade-off, 非全面胜出）:**
- ✅ 能在内存预算不足时工作（hnswlib 在 DEEP10M 直接 OOM）
- ✅ 绝对内存占用低（256MB vs 763MB = 33%）
- ❌ 吞吐代价显著（sustained 5.7–26.9% of hnswlib）

### Cache-warmed 基准（回归护栏, 非商用吞吐）

> ⚠️ 以下数字基于 200q + query 预热, 高估 1.73–7.60×, 仅用于回归测试防性能倒退。
> 对外吞吐声明 MUST 使用 sustained 口径 (CON-SLA-020)。

| 配置 | QPS | Recall | 备注 |
|------|-----|--------|------|
| 512MB 1T | 3,241 | 95.75% | 高估 1.87× |
| 512MB 16T | 30,332 | 95.75% | 高估 4.53× |
| 256MB 4T | 8,838 | 95.80% | 高估 3.51× |
| 256MB 16T | 18,675 | 95.80% | 高估 7.60× |

### DEEP10M (96维, 1000万向量)

| QPS | Recall | RSS | cgroup | hnswlib |
|-----|--------|-----|--------|---------|
| 2,340 (12T) | 95.15% | 1,612MB | 2GB | OOM (需 ~7GB) |

> DEEP10M 为 cache-warmed 口径, sustained 测量待补

---

## 环境变量参考

### 核心搜索

| 变量 | 默认 | 说明 |
|------|------|------|
| `TWO_STAGE` | 0 | 1=PQ 粗筛 + 精确精排两阶段搜索 |
| `PQ_CODES_PATH` | - | PQ 编码文件路径（必填） |
| `REFINE_EF` | 200 | 粗筛 ef 值（推荐 100） |
| `CACHE_MB` | **必填** | BlockCache 大小 (MB) |
| `FLAT_VEC_MB` | 64 | 热向量 LRU cache (MB)，512MB 推荐 160 |

### Fine Rerank (磁盘 I/O)

| 变量 | 默认 | 说明 |
|------|------|------|
| `FINE_RERANK` | 0 | 1=4KB 页粒度精排（核心优化） |
| `FINE_BUFFERED` | 0 | 1=buffered I/O 吃 page cache |
| `FINE_PREAD` | 0 | 1=pread 替代 io_uring（多线程必须） |
| `VEC_BLOCKS_PATH` | - | Vec-Only 块文件路径（必填） |

### L4 Page Cache + 预取

| 变量 | 默认 | 说明 |
|------|------|------|
| `L4_WILLNEED` | 0 | 1=pread 前 fadvise(WILLNEED) 启动内核异步 readahead |
| `L4_EVICT_META` | 0 | 1=init 后驱逐 graph 页缓存 |
| `WILLNEED_BG` | 0 | 1=无锁后台线程提交 WILLNEED (SPSC, 8T+ 推荐) |
| `PAGE_MERGE_BG` | 0 | 1=BG 线程合并连续页 fadvise (256MB 推荐, 512MB 有害) |
| `ADAPTIVE_EF` | 0 | 1=PQ gap 启发式候选数 (BEH-033, sustained +12.5~31.4%) |
| `LEARNED_EF` | 0 | 1=GBDT 多特征候选数预测 (BEH-034, sustained +12.3~47.4%) |
| `GBDT_MARGIN` | 0.8 | LEARNED_EF 预测值缩放系数 |

### 多线程

| 变量 | 默认 | 说明 |
|------|------|------|
| `NUM_THREADS` | 0 | >0=并发搜索线程数 |
| `VL_POOL_THREADS` | 999 | VisitedList 池化阈值 (推荐 14) |

### 调试

| 变量 | 说明 |
|------|------|
| `PROFILE_TS` | 1=输出两阶段计时分解 |
| `PROFILE_FINE` | 1=输出 Fine Rerank 细粒度计时 |

---

## 架构概述

### 内存布局

```
┌──────────────────────────────────────────────────────────┐
│                 常驻内存 (SIFT1M: ~155-242MB)             │
│  上层图+向量 (30MB)  L0 CSR (47MB)  PQ Codes (30MB)     │
│  route/slot/labels (18MB)  flat_vec_cache (64-160MB)    │
│  VisitedList 池 (~10MB)  BlockCache (64MB, O_DIRECT)    │
├──────────────────────────────────────────────────────────┤
│              按需 I/O (page cache 热区)                   │
│  VecBlocks (磁盘, 496MB)  ← FINE_BUFFERED 吃 page cache │
│  WILLNEED_BG ← 无锁后台线程异步预取                       │
│  PAGE_MERGE_BG ← 合并连续页减少 syscall                   │
└──────────────────────────────────────────────────────────┘
```

### 两阶段搜索流程

```
查询到达
  ├─ Step 1: 贪心下降 [纯内存] 上层图找 Layer 0 入口
  ├─ Step 2: Phase A - PQ 粗筛 [纯内存]
  │   CSR 邻接表遍历 + PQ ADC 近似距离 -> top-100 候选
  └─ Step 3: Phase B - 精确精排 [按需 I/O]
      flat_vec_cache 命中? -> 跳过 I/O
      miss -> WILLNEED_BG 预取 -> pread 4KB 页 -> 精确 L2 重排 -> top-K
```

### I/O 优化层次

| 层级 | 机制 | 条款 | 效果 |
|------|------|------|------|
| flat_vec_cache | 进程内 LRU 热向量缓存 | DEC-068 | 256MB 下 7.5× QPS (cache-warmed) |
| WILLNEED | fadvise 内核异步 readahead | DEC-070 | 256MB 下 17.7× QPS (cache-warmed) |
| WILLNEED_BG | 无锁 SPSC 后台线程提交 | DEC-074 | 16T 下 +72.8% QPS (cache-warmed) |
| PAGE_MERGE_BG | 合并连续页减少 syscall | DEC-075 | 256MB 16T 下 +17.5% (cache-warmed) |
| VL_POOL | 自适应 VisitedList 池化 | DEC-074 | 12T+ 下 +7.1% (cache-warmed) |
| ADAPTIVE_EF | PQ gap 启发式候选数 | BEH-033 | sustained +12.5~31.4% ✅ |
| LEARNED_EF | GBDT 多特征候选数预测 | BEH-034 | sustained +12.3~47.4% ✅ (重训练复活) |

> ⚠️ cache-warmed 口径的优化收益在 sustained 下可能不同。ADAPTIVE_EF 已在 sustained 下验证有效。

---

## 项目结构

```
hnsw-predictor-ndf/
├── src/
│   ├── core/               # 核心搜索引擎
│   │   ├── disk_hnsw.cpp   #   PQ 粗筛 + Fine Rerank + WILLNEED_BG
│   │   ├── block_cache.cpp #   LRU 块缓存 + flat_vec_cache
│   │   └── graph_prefetcher.cpp
│   ├── pipeline/           # 索引构建 (Step 1-7)
│   ├── benchmark/          # 基准测试
│   │   ├── benchmark_diskhnsw.cpp      # 200q cache-warmed (回归护栏)
│   │   └── benchmark_sustained.cpp     # 多轮采样 sustained (权威口径)
│   └── test/               # 单元测试
├── include/                # 头文件
│   ├── simd.h              #   SIMD 架构分发 (x86/ARM/scalar)
│   ├── simd_x86.h          #   AVX2 实现
│   ├── simd_arm.h          #   NEON 实现
│   └── simd_scalar.h       #   标量 fallback
├── scripts/                # 数据准备 + 测试脚本
│   ├── run_sustained.sh    #   sustained benchmark 运行脚本
│   ├── comprehensive_sweep.sh #  全面测试矩阵
│   └── cgroup_utils.sh     #   cgroup v1/v2 兼容层
├── docs/
│   └── detailed-design.md  # 详细设计文档
└── Makefile
```

---

## 常见问题

| 现象 | 根因 | 修复 |
|------|------|------|
| recall ≈ 0% | PQ 的 M 与维度不匹配 | SIFT dim=128 用 M=32；DEEP dim=96 用 M=24 |
| recall ≈ 0.x% | graph 与 blocks 不配套 | 同一批重新生成 Step 2-5 |
| 4T recall 崩到 12% | O_DIRECT + io_uring 非线程安全 | 设 `FINE_PREAD=1` |
| QPS 异常低 | CPU 热保护降频 | `grep MHz /proc/cpuinfo` |
| cgroup 下 QPS 虚高 | page cache 白嫖 / query 预热 | `echo 3 > drop_caches` + 用 `benchmark_sustained` |
| 4T+ 必崩 | FineRerank 懒初始化 race | 已修复 (std::call_once) |

## 平台支持

| 平台 | SIMD | 状态 | 说明 |
|------|------|------|------|
| x86_64 | AVX2 (256-bit) | ✅ 生产就绪 | i7-13700 实测验证 |
| ARMv9 AArch64 | NEON (128-bit) | ✅ 代码就绪 | 待真实 ARM 平台验证 |
| 任意 | Scalar | ✅ fallback | 无 SIMD, 性能较低 |

SIMD 抽象层 (`include/simd.h`) 在编译时根据 CPU 架构自动选择:
- `__x86_64__` -> `simd_x86.h` (AVX2 intrinsic)
- `__aarch64__` -> `simd_arm.h` (NEON intrinsic)
- 其他 -> `simd_scalar.h` (纯标量)

数据格式跨架构兼容: x86 上生成的索引/图/PQ 编码可直接在 ARM 上使用。

---

## 已知限制

1. **vecblocks 与 route table 必须配套** - 混用不同版本导致 offset 错误
2. **io_uring 非线程安全** - 多线程必须 `FINE_PREAD=1`
3. **blocks 和 vecblocks 的 block_id 不一致** - 各有独立 route 表
4. **PAGE_MERGE_BG 仅 256MB 推荐** - 512MB 下有害 (-2.9%)
5. **WILLNEED 在 I/O 量主导场景无效** - DEEP10M 瓶颈是 majfault 总量，非时序
6. **io_uring (buffered) 不优于 WILLNEED+pread** - 实测 4 种方案均不超越基线 (DEC-076)
7. **ARM NEON 性能预期低于 x86** - 128-bit vs 256-bit, 多线程可弥补
8. **LEARNED_EF (GBDT) 重训练后复活** - 用官方 query 池重训, sustained +12.3~47.4%
9. **cache-warmed QPS 不可对外引用** - 高估 1.73-7.60×, 仅作回归护栏

---

## 优化历史

| 里程碑 | QPS (cache-warmed) | QPS (sustained) | Recall | 技术 |
|--------|-------------------|-----------------|--------|------|
| 基线 | 53 | - | 95.7% | 64KB 块同步读 |
| Fine Rerank | 867 | - | 95.7% | 4KB 页粒度精排 |
| SIMD PQ LUT | 2643 | - | 95.7% | AVX2 距离表 |
| CSR 压缩 | 2092 | - | 95.7% | delta+varint 1.8× |
| flat_vec_cache | 2309 | - | 95.7% | Fine Rerank 命中热向量 |
| WILLNEED | 2379 | - | 95.7% | 内核 readahead (256MB 17.7×) |
| DEEP10M | 2340 | - | 95.15% | 10M 规模验证 |
| FineRerank 线程安全 | 9914@4T | - | 95.75% | std::call_once |
| FVC 默认 64MB | 11421@4T | - | 95.75% | +23.4% QPS |
| WILLNEED_BG (A2) | 30332@16T | 6694@16T | 95.75% | 无锁后台线程 +72.8% |
| VL_POOL (C2) | 30332@16T | - | 95.75% | 自适应池化 +7.1% |
| PAGE_MERGE_BG | 18675@16T | 2456@16T | 95.80% | 256MB 下 +17.5% |
| ADAPTIVE_EF | - | 9862@16T | 95.80% | PQ gap 启发式 sustained +26.4% |
| Sustained Benchmark | - | 6694@16T | 96.00% | 诚实测量方法论 (DEC-084) |

---

## 测量口径说明

本项目有两种测量口径，MUST NOT 混比：

| 口径 | 工具 | 预热 | 用途 |
|------|------|------|------|
| **Sustained** | `benchmark_sustained` | 禁预热 | 对外吞吐声明 (CON-SLA-020) |
| **Cache-warmed** | `benchmark_diskhnsw` | 200q 预热 | 回归护栏 (CON-SLA-016/017/018) |

Sustained 口径使用官方 SIFT 10K query 池多轮随机采样（N=1000, R=15, seed=42），
禁止对被测 query 预热（CON-SLA-019），recall 96.00% 基于Official groundtruth。

Cache-warmed 口径在计时前将全部 200q 跑一遍预热 page cache，
导致测得 in-memory 性能，高估 1.73–7.60×（DEC-084）。

---

## 约束感知调优

DiskHNSW 附带一个**离线**约束感知调优器（[[BEH-028]] / [[ARCH-009]]）：用「结构感知搜索 +
廉价可行性剪枝 + 实测校验」在远少于 grid / Optuna 的完整 rebuild 次数内，找到满足 recall ≥95%
且优于锁定默认 QPS 的配置。它不进查询热路径。

```bash
# 用户主入口：P0–P4 嵌套遍历（复用 Trunk build_pipeline.sh + run_sustained.sh）
python3 tools/constraint-aware-tuner/scripts/traverse.py

# 廉价剪枝自检（无 build / 无测量）
python3 tools/constraint-aware-tuner/scripts/traverse.py --self-test
```

> 原理、六条耦合、P0–P4、`CAT_BUDGET_REBUILDS` / `CAT_GBDT_PROBES`、与 grid/Optuna 的差别、
> 配置记录（[[VER-004]]）见 [docs/constraint-aware-tuner.md](docs/constraint-aware-tuner.md)。
> 调优器产出的 POC evidence 数字**不是** stable must SLA（[[CON-POC-001]]）。

---

## 未来方向

| 阶段 | 目标 | 状态 |
|------|------|------|
| P2: 10M 规模 | DEEP10M @2GB, recall≥95% | ✅ 完成 |
| P2.1: 多线程 Scaling | 1-24T 曲线 + hnswlib 对比 | ✅ 完成 |
| P2.2: 性能差距优化 | FVC 调优 + 256MB cgroup | ✅ 完成 |
| P2.3: 多线程拓展性 | WILLNEED_BG + VL_POOL | ✅ 完成 |
| P2.4: L4 cache 管理 | page cache 优化 | ✅ 完成 (Pareto 前沿) |
| P2.5: Fine Rerank I/O | io_uring 替代 pread | ❌ 负结果 (DEC-076) |
| P2.6: ARMv9 架构支持 | NEON SIMD 兼容 | ✅ 代码就绪 (待验证) |
| P2.7: 自适应 EF | PQ 距离间隙启发式 | ✅ promoted (BEH-033) |
| P2.8: GBDT 学习式剪枝 | per-query 参数预测 | ✅ promoted (BEH-034 must, 重训练复活) |
| P2.9: Sustained Benchmark | 诚实测量方法论 | ✅ promoted (BEH-035, DEC-084) |
| P3: CSR 上磁盘 | 100M 必需 | 待启动 |
| P4: 分级存储 | hot/warm/cold 三层 | 长期 |
