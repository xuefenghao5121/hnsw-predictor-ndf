# DiskHNSW - 内存受限环境下的磁盘向量搜索

> 在 cgroup 内存限额下，用磁盘驻留向量做接近全内存 HNSW 的召回（≥95%）。
> SIFT1M @512MB: 95.75% recall / 3241 QPS (1T) / 20903 QPS (16T+BG) / RSS 242MB
> SIFT1M @256MB: 95.80% recall / 8838 QPS (4T) / RSS 200MB (35% of hnswlib memory)
> SIFT1M peak (512MB+BG): 30,332 QPS (16T) = 73% of hnswlib, 1.05x QPS/MB efficiency
> DEEP10M @2GB: 95.15% recall / 2340 QPS (12T) / RSS 1612MB (hnswlib OOM)

## 项目背景

传统 HNSW 向量搜索需要将全部向量加载到内存。对于 1M 条 128 维 SIFT 向量，hnswlib 需 726MB RSS；10M 条 96 维 DEEP 向量需 ~7GB。在容器化、边缘计算等内存受限场景下不可行。

DiskHNSW 的核心思路：

1. **图结构常驻内存**（上层节点向量 + L0 邻接表 CSR 压缩）
2. **向量数据存磁盘**，按 BFS 重排后分块，利用空间局部性
3. **PQ 粗筛**：Product Quantization 压缩向量常驻内存，做零 I/O 近似距离搜索
4. **精确精排**（Fine Rerank）：对粗筛候选集按 4KB 页粒度读真实向量做精确 L2
5. **I/O 优化**：io_uring/pread + page cache + flat_vec_cache 热向量缓存 + WILLNEED readahead

---

## 快速开始

### 编译

```bash
# 依赖: Linux 5.1+ (io_uring), g++ C++17, Python 3 + faiss
make all        # 编译全部: pipeline 工具 + benchmark + 测试
```

### 一键准备数据（SIFT1M 示例）

```bash
# 下载 SIFT1M base/query 数据到 data/
# 然后一键生成全套索引文件
bash scripts/build_pipeline.sh data/sift_base.fvecs sift1m 32
# 产出: output/sift1m_{index,graph,bfs,blocks_64k,route_64k,vecblocks_64k}.bin
#       output/pqco_sift1m_M32_correct.bin
```

### 运行 Benchmark

```bash
# 正式对比测试（推荐）
bash scripts/compare_benchmark.sh

# 手动运行（推荐配置）
TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1 \
VEC_BLOCKS_PATH=output/sift1m_vecblocks_64k.bin \
PQ_CODES_PATH=output/pqco_sift1m_M32_correct.bin \
CACHE_MB=64 FLAT_VEC_MB=160 REFINE_EF=100 \
./build/benchmark_diskhnsw \
    output/sift1m_graph.bin output/sift1m_bfs.bin \
    output/sift1m_blocks_64k.bin output/sift1m_route_64k.bin \
    data/sift_base.fvecs data/sift1m_query200.fvecs data/sift1m_gt200.bin \
    10 100 200
```

### 严格 cgroup 隔离测试（CON-SLA-014）

生产部署模拟：`drop_caches` 清场 + cgroup 限制，确保性能数字无白嫖。

```bash
# SIFT1M 512MB cgroup
sync; echo 3 | sudo tee /proc/sys/vm/drop_caches
sudo mkdir -p /sys/fs/cgroup/hnsw_test
echo $((512 * 1024 * 1024)) | sudo tee /sys/fs/cgroup/hnsw_test/memory.max
echo $$ | sudo tee /sys/fs/cgroup/hnsw_test/cgroup.procs

TWO_STAGE=1 FINE_RERANK=1 FINE_BUFFERED=1 FINE_PREAD=1 \
L4_EVICT_META=1 L4_WILLNEED=1 \
VEC_BLOCKS_PATH=output/sift1m_vecblocks_64k.bin \
PQ_CODES_PATH=output/pqco_sift1m_M32_correct.bin \
CACHE_MB=64 FLAT_VEC_MB=160 REFINE_EF=100 \
./build/benchmark_diskhnsw \
    output/sift1m_graph.bin output/sift1m_bfs.bin \
    output/sift1m_blocks_64k.bin output/sift1m_route_64k.bin \
    data/sift_base.fvecs data/sift1m_query200.fvecs data/sift1m_gt200.bin \
    10 100 200

# 查看内存统计
cat /sys/fs/cgroup/hnsw_test/memory.peak
cat /sys/fs/cgroup/hnsw_test/memory.events
grep -E "^(anon|file|workingset_refault_file|pgmajfault)" /sys/fs/cgroup/hnsw_test/memory.stat
```

### 启用 WILLNEED（page cache 受限场景加速）

```bash
# 在标准配置基础上加 L4_WILLNEED=1
# SIFT1M 256MB cgroup: 17.7x QPS 提升
# SIFT1M 512MB cgroup: +5.5%，无回归
# DEEP10M 2GB cgroup: ~0%，中性（I/O 量是瓶颈，非时序）
L4_WILLNEED=1 ./build/benchmark_diskhnsw ...
```

---

## 数据准备 Pipeline（7 步）

> **三条铁律**：① 一套数据从头到尾（同一 base.fvecs）② graph 与 blocks 同批生成 ③ PQ 的 M 匹配维度

| 步骤 | 命令 | 产出 |
|------|------|------|
| 1. 建图 | `./build/build_index data/sift_base.fvecs output/sift1m_index.bin 16 200` | hnswlib 索引 |
| 2. 提取图 | `./build/extract_graph output/sift1m_index.bin output/sift1m_graph.bin 128` | 精简图结构 |
| 3. BFS 重排 | `./build/bfs_reorder output/sift1m_graph.bin output/sift1m_bfs.bin` | old↔new 映射 |
| 4. Vec-Only 块 | `./build/write_blocks_veconly output/sift1m_graph.bin output/sift1m_bfs.bin output/sift1m_vecblocks_64k.bin 65536` | 向量块+route |
| 5. 旧格式块 | `./build/write_blocks ... && ./build/gen_route ...` | BlockCache 用 |
| 6. PQ 编码 | `python3 scripts/train_pq.py data/sift_base.fvecs output/pqco_sift1m_M32_correct.bin 32` | PQ codes |
| 7. Ground Truth | `python3 scripts/gen_gt.py data/sift_base.fvecs data/sift1m_query200.fvecs data/sift1m_gt200.bin 10` | 真实 top-K |

> 或直接用 `bash scripts/build_pipeline.sh data/sift_base.fvecs sift1m 32` 一键执行。

---

## 性能数据

### SIFT1M (128维, 100万向量)

**严格 cgroup 隔离 (CON-SLA-014), 512MB, 1T:**

| 配置 | QPS | Recall | RSS | 备注 |
|------|-----|--------|-----|------|
| 基线 (WILLNEED=0) | 2406 | 95.75% | 155MB | page cache 充裕 |
| +WILLNEED=1 | 2459 | 95.75% | 155MB | +2.2%，无回归 |

**256MB cgroup (page cache 不足):**

| 配置 | QPS | Recall | RSS | refault | 备注 |
|------|-----|--------|-----|---------|------|
| 基线 | 134 | 95.75% | 153MB | 27718 | pread 串行阻塞 |
| +WILLNEED=1 | **2379** | 95.75% | 153MB | 74 | **17.7x**，readahead 流水线 |

**多线程 Scaling (CON-SLA-014, 512MB cgroup, +WILLNEED):**

| 线程数 | QPS (baseline) | QPS (+BG+POOL) | Recall | Scaling (optimized) |
|--------|---------------|----------------|--------|---------------------|
| 1T | 3,147 | 3,133 | 95.75% | 1.0x |
| 4T | 9,914 | 9,041 | 95.75% | 2.9x |
| 8T | 14,224 | 14,901 | 95.75% | 4.8x |
| 12T | 17,207 | 18,459 | 95.75% | 5.9x |
| **16T (peak)** | 18,317 | **30,332** | 95.75% | **9.7x** |
| 24T | 19,766 | 29,738 | 95.75% | 9.5x |

> `+BG+POOL` = `WILLNEED_BG=1 VL_POOL_THREADS=14` (BEH-027, DEC-074)

**256MB cgroup (CON-SLA-016, +WILLNEED, FLAT_VEC_MB=64):**

| 线程数 | QPS | Recall | RSS |
|--------|-----|--------|-----|
| 1T | 2,564 | 95.80% | 195MB |
| 4T | 6,882 | 95.80% | 200MB |
| 12T | 10,477 | 95.80% | 215MB |
| **16T (peak)** | **16,873** | 95.80% | 223MB |

**对比 hnswlib (16T, 完整 scaling):**

| 配置 | QPS (16T) | Recall | 内存 | QPS/MB 效率 | vs hnswlib |
|------|-----------|--------|------|------------|-----------|
| hnswlib (unlimited) | 39,322 | 98.30% | 732MB | 53.7 | 1.0x |
| DiskHNSW 512MB (+BG) | **30,332** | 95.75% | 512MB (70%) | **59.2** | **1.10x** |
| **DiskHNSW 256MB** | **16,873** | 95.80% | **256MB (35%)** | **65.9** | **1.23x** |

> DiskHNSW 的 QPS/MB 内存效率在 256MB 和 512MB 配置下均超过 hnswlib

### DEEP10M (96维, 1000万向量)

**严格 cgroup 隔离, 2GB, 12T:**

| QPS | Recall | RSS | cgroup | hnswlib |
|-----|--------|-----|--------|---------|
| 2340 | 95.15% | 1612MB | 2GB | OOM (需 ~7GB) |

**优化路径:**

| 优化 | QPS | 收益 |
|------|-----|------|
| VisitedList uint32->uint8 | 1170->2340 | 2x (内存分配瓶颈) |
| flat_vec_cache 128MB | 698 | +20% |
| REFINE_EF=300 | 95.15% recall | 达标 |
| PQ M=24 | 963 | +82% vs M=32 |

---

## 环境变量参考

### 核心搜索

| 变量 | 默认 | 说明 |
|------|------|------|
| `TWO_STAGE` | 0 | 1=PQ粗筛+精确精排两阶段搜索 |
| `PQ_CODES_PATH` | - | PQ 编码文件路径（必填） |
| `PQ_HYBRID` | 0 | 1=cache 命中用精确距离，miss 用 PQ |
| `REFINE_EF` | 200 | 粗筛 ef 值（100-300，越大 recall 越高） |
| `CACHE_MB` | **必填** | BlockCache 大小 (MB) |
| `FLAT_VEC_MB` | 0 | 热向量 LRU cache (MB)，64MB 推荐 |

### Fine Rerank

| 变量 | 默认 | 说明 |
|------|------|------|
| `FINE_RERANK` | 0 | 1=4KB 页粒度精排（核心优化） |
| `FINE_BUFFERED` | 0 | 1=buffered I/O 吃 page cache |
| `FINE_PREAD` | 0 | 1=pread 替代 io_uring（多线程必须） |
| `VEC_BLOCKS_PATH` | - | Vec-Only 块文件路径（FINE_RERANK 必填） |

### L4 Page Cache 管理

| 变量 | 默认 | 说明 |
|------|------|------|
| `L4_WILLNEED` | 0 | 1=pread 前 fadvise(WILLNEED) 启动内核异步 readahead |
| `L4_EVICT_META` | 0 | 1=init 后驱逐 graph/BFS 页缓存释放预算给 vecblocks |
| `FINE_FADVISE` | 0 | 1=精排后驱逐页（512MB 有害，256MB 中性） |

### 多线程

| 变量 | 默认 | 说明 |
|------|------|------|
| `NUM_THREADS` | 0 | >0=并发搜索线程数（需配合 FINE_PREAD=1） |
| `WILLNEED_BG` | 0 | 1=WILLNEED 后台线程提交 (无锁 SPSC, 消除内核锁竞争, 8T+ 推荐) |
| `VL_POOL_THREADS` | 999 | VisitedList 池化阈值, NUM_THREADS≥此值时启用 (推荐 14) |

### 调试

| 变量 | 说明 |
|------|------|
| `PROFILE_TS` | 1=输出两阶段计时分解 |
| `PROFILE_FINE` | 1=输出 fine rerank 细粒度计时 |

---

## 架构概述

### 内存布局

```
┌──────────────────────────────────────────────────────────┐
│                 常驻内存 (SIFT1M: ~155MB)                 │
│  上层图+向量 (30MB)  L0 CSR压缩 (47MB)  PQ Codes (30MB) │
│  route_table (4MB)   slot_table (2MB)    labels (12MB)  │
│  flat_vec_cache (64MB)  VisitedList池 (~40MB)            │
├──────────────────────────────────────────────────────────┤
│              按需 I/O (page cache 热区)                  │
│  VecBlocks (磁盘, 496MB)  ← FINE_BUFFERED 吃 page cache │
│  WILLNEED readahead ← L4_WILLNEED=1 异步预取            │
└──────────────────────────────────────────────────────────┘
```

### 两阶段搜索流程

```
查询到达
  ├─ Step 1: 贪心下降 [纯内存] 上层图找 Layer 0 入口
  ├─ Step 2: Phase A - PQ 粗筛 [纯内存]
  │   CSR 邻接表遍历 + PQ ADC 近似距离 → top-100 候选
  └─ Step 3: Phase B - 精确精排 [按需 I/O]
      flat_vec_cache 命中? → 跳过 I/O
      miss → 4KB 页 pread (WILLNEED 预取) → 精确 L2 重排 → top-K
```

### WILLNEED 原理

`posix_fadvise(POSIX_FADV_WILLNEED)` 在 pread 循环前对所有需要的页批量调用，内核启动异步 readahead。pread 从阻塞磁盘 I/O 变为内存拷贝。

**适用条件**：page cache 严重受限 + pread 是瓶颈 + refault 暴涨。三者同时满足时效果显著（17.7x），否则无副作用。

---

## 优化历史

| 里程碑 | QPS | Recall | RSS | 技术 |
|--------|-----|--------|-----|------|
| 基线 | 53 | 95.7% | 337MB | 64KB 块同步读 |
| FINE_RERANK | 867 | 95.7% | 337MB | 4KB 页粒度精排 |
| FINE_BUFFERED | 2141 | 95.7% | 337MB | page cache 热区 |
| SIMD PQ LUT | 2643 | 95.7% | 337MB | AVX2 距离表 |
| CSR 压缩 (P0) | 2092 | 95.7% | 269MB | delta+varint 1.8x |
| Bug 修复 (P0.5) | 2067 | 95.7% | 269MB | 双路由表分离 |
| 4T 并发 | 5808 | 95.7% | 286MB | pread 多线程 |
| **flat_vec_cache** | 2309 | 95.7% | 155MB | fine rerank 命中热向量 |
| **WILLNEED** | 2379@256MB | 95.7% | 153MB | 内核 readahead 流水线 |
| **DEEP10M** | 2340 | 95.15% | 1612MB | 10M 规模验证 |
| **FineRerank thread safety** | 9914@4T | 95.75% | 220MB | std::call_once 修复 race |
| **FVC default 64MB** | 11421@4T | 95.75% | 220MB | +23.4% QPS (perf-gap-4t D1) |
| **256MB cgroup SLA** | 8838@4T | 95.80% | 200MB | 35% memory, 2.0x efficiency |
| **WILLNEED_BG (A2)** | 30332@16T | 95.75% | 242MB | 无锁后台线程, +72.8% QPS |
| **VL_POOL (C2)** | 30332@16T | 95.75% | 242MB | 自适应 VisitedList 池化 |

---

## 项目结构

```
hnsw-predictor-ndf/
├── src/
│   ├── core/              # 核心库
│   │   ├── disk_hnsw.cpp  #   搜索引擎（PQ、精排、WILLNEED）
│   │   ├── block_cache.cpp#   LRU 块缓存 + flat_vec_cache
│   │   └── graph_prefetcher.cpp
│   ├── pipeline/          # 索引构建 (Step 1-7)
│   ├── benchmark/         # 基准测试
│   └── test/              # 单元测试
├── include/               # 头文件
├── scripts/               # 数据准备 + 测试脚本
│   ├── build_pipeline.sh  #   一键跑完整 pipeline
│   ├── compare_benchmark.sh # 正式对比测试
│   ├── train_pq.py        #   PQ 训练
│   ├── gen_gt.py          #   Ground Truth 生成
│   └── run_trunk_perf.sh  #   严格 cgroup 性能验证
├── docs/
│   ├── detailed-design.md #   主线详细设计（含 cgroup 严格测试协议）
│   └── archive-*.orig     #   历史文档存档
└── Makefile
```

---

## 常见问题

| 现象 | 根因 | 修复 |
|------|------|------|
| recall ≈ 0% | PQ 的 M 与维度不匹配 | SIFT dim=128 用 M=32；DEEP dim=96 用 M=24 |
| recall ≈ 0.x% | graph 与 blocks 不配套 | 同一批重新生成 Step 2-5 |
| recall 偏低且乱跳 | benchmark K 与 GT K 不一致 | gen_gt.py 和 benchmark 用相同 K |
| 4T recall 崩到 12% | O_DIRECT + io_uring 非线程安全 | 设 FINE_PREAD=1 |
| QPS 异常低 | CPU 热保护降频 | `grep MHz /proc/cpuinfo`，关闭 intel_pstate |
| cgroup 下 QPS 虚高 | page cache 白嫖（数据在 cgroup 外预热） | `echo 3 > drop_caches` 清场 |

---

## 已知限制

1. **vecblocks 与 route table 必须配套**：混用不同版本文件导致 offset 错误
2. **io_uring 非线程安全**：多线程必须 `FINE_PREAD=1`
3. **blocks 和 vecblocks 的 block_id 不一致**：各有独立 route 表，不可混用
4. **cgroup memory.file ≠ page cache 总量**：首次读入在 cgroup 外时不计入
5. **WILLNEED 在 I/O 量主导场景无效**：DEEP10M 瓶颈是 majfault 总量（68K），非 pread 时序

---

## 未来方向

| 阶段 | 目标 | 状态 |
|------|------|------|
| P0: CSR 压缩 | delta+varint 1.8x | ✅ 完成 |
| P0.5: 双路由表修复 | vec_route_table 分离 | ✅ 完成 |
| P1: 图裁剪 | MRNG R_max 减边 | ✅ 负结果（1M 无净收益） |
| P2: 10M 规模 | DEEP10M @2GB, recall≥95% | ✅ 完成 (95.15%, 2340 QPS) |
| P2.1: 多线程 Scaling | SIFT1M 1-24T 曲线 + hnswlib 对比 | ✅ 完成 (peak 16T=30332) |
| P2.2: 性能差距优化 | FVC 调优 + 256MB cgroup | ✅ 完成 (+23.4%, 2.0x 效率) |
| P2.3: 多线程拓展性优化 | WILLNEED_BG + VL_POOL | ✅ 完成 (+72.8% at 16T) |
| P3: CSR 上磁盘 | 100M 必需，4.7GB 装不进内存 | 待启动 |
| P4: 分级存储 | hot/warm/cold 三层 + 增量插入 | 长期 |
| P5: 硬件亲和 | NUMA/SPDK/GPU/PMEM | 探索 |
