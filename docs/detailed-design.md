# DiskHNSW 详细设计文档

> 版本: v1.0 | 日期: 2026-08-04  
> 基于 NDF 规范 spec/00-50 + DEC-059~070 编写

---

## 1. 系统目标

在 cgroup 内存限额（≥512MB）下，使用磁盘驻留向量数据，实现与全内存 HNSW 可比的搜索召回率（≥95%），同时将常驻内存控制在限额内。

**核心指标（SIFT1M, 512MB cgroup, 严格隔离 CON-SLA-014）**：

| 指标 | 目标 | 实测 |
|------|------|------|
| Recall@10 | ≥ 95% | 95.75% |
| QPS (1T) | ≥ 2000 | 2406 |
| QPS (4T) | ≥ 5000 | 5808 |
| RSS | ≤ 300MB | 155MB |
| cgroup peak | ≤ 512MB | 512MB |
| oom | = 0 | 0 |

**对比 hnswlib**：hnswlib 需 726MB RSS（OOM@512MB），DiskHNSW 内存节省 4.7x。

---

## 2. 架构概览

### 2.1 模块分层

```
┌─────────────────────────────────────────────────────────┐
│ L5: 应用层 (benchmark, tests, pipeline tools)           │
├─────────────────────────────────────────────────────────┤
│ L4: 搜索引擎 DiskHNSW                                   │
│   搜索流程 │ PQ 粗筛 │ Fine Rerank 精排 │ CSR 邻接表    │
├─────────────────────────────────────────────────────────┤
│ L3: 图引导预取 GraphPrefetcher                          │
├─────────────────────────────────────────────────────────┤
│ L2: 缓存层 BlockCache + IoUring + FlatVecCache          │
├─────────────────────────────────────────────────────────┤
│ L1: 策略接口 LayoutProvider / ReplacementPolicy          │
├─────────────────────────────────────────────────────────┤
│ L0: 数据格式 common.h (fvecs, varint, CSR)              │
└─────────────────────────────────────────────────────────┘
```

### 2.2 内存布局

常驻内存（SIFT1M, 512MB cgroup, 约 155MB RSS）：

| 组件 | 大小 | 说明 |
|------|------|------|
| 上层图 + 向量 | 30MB | Layer 1+ 节点（贪心下降用） |
| L0 CSR 邻接表 | 47MB | Delta+Varint 压缩的邻接表 |
| PQ Codes | 30MB | M=32 子量化器编码（全量常驻） |
| flat_vec_cache | 64MB | 热向量 LRU 缓存（命中跳过 I/O） |
| route/slot/labels | 18MB | 路由表 + slot 偏移 + 标签映射 |
| VisitedList 池 | ~10MB | uint8 访问标记（DEEP10M 优化关键） |
| BlockCache | 64MB | 64KB 粗筛块 LRU 缓存（O_DIRECT） |

按需 I/O（不常驻，走 page cache）：

| 组件 | 大小 | 说明 |
|------|------|------|
| VecBlocks | 496MB | BFS 重排后的 4KB 向量页（Fine Rerank 读取） |

### 2.3 数据 Pipeline（7 步）

```
base.fvecs
  │
  ├─ Step 1: build_index (hnswlib M=16 efC=200)
  │    └─ index.bin
  ├─ Step 2: extract_graph (maxM=128)
  │    └─ graph.bin
  ├─ Step 3: bfs_reorder
  │    └─ bfs.bin (old↔new 映射)
  ├─ Step 4: write_blocks_veconly (blockSize=64KB)
  │    └─ vecblocks_64k.bin (Fine Rerank 数据源)
  ├─ Step 5: write_blocks + gen_route
  │    └─ blocks_64k.bin + route_64k.bin (BlockCache 用)
  ├─ Step 6: train_pq (faiss, M=32 SIFT / M=24 DEEP)
  │    └─ pqco_*_M*.bin
  └─ Step 7: gen_gt (faiss IndexFlatL2)
       └─ gt200.bin
```

**三条铁律**：① 一套数据从头到尾 ② graph 与 blocks 同批生成 ③ PQ 的 M 匹配维度

---

## 3. 两阶段搜索流程

### 3.1 状态机

```
[查询到达]
  │
  ├─ Phase 0: greedyDescent (L_max → L1)
  │    纯内存，零 I/O。遍历上层图找 Layer 0 入口节点。
  │
  ├─ Phase A: searchLayer0 (PQ ADC 粗筛)
  │    CSR 邻接表遍历 + PQ ADC 查表近似距离
  │    → 输出 top-REFINE_EF 候选集
  │    纯内存（PQ Codes 常驻 + CSR 常驻 + BlockCache O_DIRECT）
  │
  └─ Phase B: FineRerank (4KB 页粒度精排)
       遍历候选:
       ├─ flat_vec_cache 命中? → 精确 L2 (零 I/O)
       ├─ BlockCache 命中? → 精确 L2 (零 I/O)
       └─ miss → 4KB 页读取:
            ├─ L4_WILLNEED=1 → fadvise(WILLNEED) 批量预取
            ├─ FINE_PREAD=1 → pread 同步读
            └─ FINE_PREAD=0 → io_uring 异步读
            → 精确 L2 → consider() → putFlatVector()
       → 输出 top-K 结果
```

### 3.2 PQ 距离计算（Phase A）

Product Quantization 将 d 维向量切分为 M 个子向量，每个子向量用 256 个 centroid 量化。

**ADC（Asymmetric Distance Computation）**：查询向量不做量化，对每个子向量预计算 query_sub 到 256 个 centroid 的距离表（`pq_dist_table_`，thread_local），然后查表累加。

- `dsub == 4`：AVX2 路径，一次处理 2 个 centroid（8 floats），`_mm256_sub_ps` + `_mm256_mul_ps` + `_mm_hadd_ps`
- `dsub != 4`：标量三重循环

**PQ_HYBRID=1**：BlockCache 命中的候选用精确 L2 替代 PQ 近似，提高 Phase A 精度。

### 3.3 CSR 邻接表压缩

Layer 0 邻接表使用 Delta+Varint 压缩，压缩比约 1.8x：

- 邻居 ID 经 BFS 重排后空间局部性好，delta 值小
- Varint 编码：小数字 1 字节，大数字 2-5 字节
- 解码：从 `adj_csr_byte_offsets_[new_id]` 读取，解码到 thread_local `csr_decode_buf_`

### 3.4 Fine Rerank（Phase B）

对 Phase A 输出的候选集，按 4KB 页粒度读取真实向量做精确 L2 重排：

1. **候选遍历**：对每个候选检查 flat_vec_cache → BlockCache → 磁盘 I/O
2. **页收集**：miss 的候选收集到 `io_cands`（记录 nid, page0, offset_in_page, cross_page）
3. **WILLNEED 预取**（opt-in）：`L4_WILLNEED=1` 时，对 `pages_needed` 中所有页调用 `posix_fadvise(WILLNEED)`，内核启动异步 readahead
4. **批量读取**：pread（同步，多线程安全）或 io_uring（异步，单线程）
5. **精确距离**：对每个候选计算 L2 距离，插入 `refined` 优先队列
6. **结果合并**：`refined` 中的候选提升到 `top_candidates`

### 3.5 WILLNEED readahead 机制

**原理**：`posix_fadvise(POSIX_FADV_WILLNEED)` 提示内核即将读取指定文件区域。内核启动异步 readahead，将页预读入 page cache。后续 pread 从内存拷贝而非阻塞磁盘 I/O。

**效果**（CON-SLA-014 标准协议验证）：

| 场景 | 基线 QPS | +WILLNEED | 提升 | 原因 |
|------|---------|-----------|------|------|
| SIFT1M 256MB | 134 | 2379 | 17.7x | pread 是瓶颈，readahead 流水线化 |
| SIFT1M 512MB | 2267 | 2392 | +5.5% | pread 非瓶颈，微正 |
| DEEP10M 2GB | 570 | 568 | ~0% | I/O 量是瓶颈（68K majfault），非时序 |

**适用条件**：① page cache 严重受限 ② pread 是延迟主导 ③ refault 暴涨

**cgroup 合规**：`file` 用量不变（103MB），`majfault` 不变（~5100），`peak` = cgroup limit，`oom` = 0。WILLNEED 不多占内存，只改变 I/O 时序。

---

## 4. 严格 cgroup 隔离测试协议（CON-SLA-014）

### 4.1 为什么需要严格隔离

cgroup v2 page cache 记账规则为"首次读取者归属"。当数据准备（root cgroup）和检索（子 cgroup）在同一台机器上时，数据准备阶段预热的 page cache 不会被重新记账到 benchmark cgroup，导致实际可用内存远超限制——称为"白嫖"。

### 4.2 记账陷阱

| 陷阱 | 描述 |
|------|------|
| 首次读取归属 | page cache 记账归属首次读取者，不是当前使用者 |
| RSS 不含 page cache | VmRSS 只含匿名页 + mmap，不含 read() 产生的 page cache |
| memory.current 漏计 | 别人（root cgroup）读过的页对你免费 |

### 4.3 协议步骤

```bash
# 1. 清场：驱逐所有 page cache（模拟"文件刚到达"）
sync && echo 3 | sudo tee /proc/sys/vm/drop_caches

# 2. 创建受限 cgroup
sudo mkdir -p /sys/fs/cgroup/hnsw_bench
echo $((512 * 1024 * 1024)) | sudo tee /sys/fs/cgroup/hnsw_bench/memory.max

# 3. 将当前 shell 加入 cgroup
echo $$ | sudo tee /sys/fs/cgroup/hnsw_bench/cgroup.procs

# 4. 运行 benchmark（所有 I/O 首次读取，全部记入 cgroup）
L4_WILLNEED=1 TWO_STAGE=1 FINE_RERANK=1 FINE_PREAD=1 FINE_BUFFERED=1 \
CACHE_MB=64 FLAT_VEC_MB=64 L4_EVICT_META=1 \
VEC_BLOCKS_PATH=... PQ_CODES_PATH=... \
./build/benchmark_diskhnsw ... 10 100 200

# 5. 收集验收数据
cat /sys/fs/cgroup/hnsw_bench/memory.peak    # ≤ limit
cat /sys/fs/cgroup/hnsw_bench/memory.events  # oom=0
grep -E "^(anon|file|workingset_refault_file|pgmajfault)" \
    /sys/fs/cgroup/hnsw_bench/memory.stat
```

### 4.4 验收报告必须包含

1. `memory.peak`（证明总内存未超限）
2. `memory.stat` 中 `anon` 和 `file` 分项（证明 page cache 在预算内）
3. `memory.events` 中 `oom` = 0（证明未触发 OOM）

### 4.5 监控指标

| 指标 | 含义 | 关注点 |
|------|------|--------|
| `memory.current` | 总内存（anon + file） | 应 ≤ memory.max |
| `anon` | 匿名页（堆/栈/数据结构） | 进程实际占用 |
| `file` | 文件页（page cache，本 cgroup 产生） | 真实 I/O 缓存 |
| `workingset_refault_file` | 文件页回收后再次访问 | 高 = cache 抖动 |
| `pgmajfault` | major page fault | 高 = I/O 瓶颈 |

---

## 5. 多线程并发

### 5.1 线程安全设计

- `FINE_PREAD=1`：多线程必须启用。pread 替代 io_uring（io_uring 非线程安全）
- `pq_dist_table_`：thread_local，每线程独立 PQ 距离表
- `csr_decode_buf_`：thread_local，每线程独立 CSR 解码缓冲区
- `VisitedList` 池：预分配，每线程从池中获取

### 5.2 VisitedList 优化（DEEP10M 关键）

10M 规模下 VisitedList 的内存分配是隐藏瓶颈：

- `uint32_t` → `uint8_t`：10M 节点 40MB → 10MB per VisitedList，12 线程省 360MB
- 每次 searchKnn 创建/销毁 VisitedList，malloc/free 是隐藏瓶颈
- 优化后 DEEP10M QPS 从 1170 提升到 2340（2x）

---

## 6. 性能数据汇总

### 6.1 SIFT1M（128 维，100 万向量）

| 配置 | QPS | Recall | RSS | cgroup | 备注 |
|------|-----|--------|-----|--------|------|
| 1T 512MB | 2406 | 95.75% | 155MB | 512MB | 生产默认 |
| 1T 512MB +WILLNEED | 2459 | 95.75% | 155MB | 512MB | +2.2% |
| 4T 512MB | 5808 | 95.70% | 286MB | 512MB | 4 线程并发 |
| 1T 256MB | 134 | 95.75% | 153MB | 256MB | page cache 不足 |
| 1T 256MB +WILLNEED | 2379 | 95.75% | 153MB | 256MB | **17.7x** |
| hnswlib 全内存 | - | 95.25% | 726MB | - | OOM@512MB |

### 6.2 DEEP10M（96 维，1000 万向量）

| 配置 | QPS | Recall | RSS | cgroup | 备注 |
|------|-----|--------|-----|--------|------|
| 12T 2GB | 2340 | 95.15% | 1612MB | 2GB | hnswlib OOM@2GB |
| hnswlib 全内存 | 1557 | 95.60% | ~6GB | - | ef=400, 1T |

**DEEP10M 优化路径**：

| 优化 | QPS | 收益 |
|------|-----|------|
| VisitedList uint32→uint8 | 1170→2340 | 2x |
| flat_vec_cache 128MB | 698 | +20% |
| PQ M=24 | 963 | +82% vs M=32 |
| REFINE_EF=300 | 95.15% recall | 达标 |
| FINE_PREAD=1 | 修复 io_uring bug | recall 恢复 |

### 6.3 cgroup 可行性（DEEP10M）

| cgroup | 可行 | RSS 峰值 | 说明 |
|--------|------|---------|------|
| 1GB | ❌ | OOM | 核心数据 1.1GB |
| 1.8GB | ✅ | 941MB init / 1395MB peak | 最小可行 |
| 2GB | ✅ | 1088MB init / 1612MB peak | 推荐 |

---

## 7. 环境变量完整参考

### 核心搜索

| 变量 | 默认 | 说明 |
|------|------|------|
| `TWO_STAGE` | 0 | 1=PQ 粗筛 + 精排两阶段 |
| `PQ_CODES_PATH` | - | PQ 编码文件路径 |
| `PQ_HYBRID` | 0 | 1=cache 命中用精确距离 |
| `REFINE_EF` | 200 | 粗筛 ef 值 |
| `CACHE_MB` | 必填 | BlockCache 大小 |
| `FLAT_VEC_MB` | 0 | 热向量 LRU cache |

### Fine Rerank

| 变量 | 默认 | 说明 |
|------|------|------|
| `FINE_RERANK` | 0 | 1=4KB 页精排 |
| `FINE_BUFFERED` | 0 | 1=buffered I/O |
| `FINE_PREAD` | 0 | 1=pread（多线程必须） |
| `VEC_BLOCKS_PATH` | - | Vec-Only 块文件 |

### L4 Page Cache 管理

| 变量 | 默认 | 说明 |
|------|------|------|
| `L4_WILLNEED` | 0 | 1=pread 前 fadvise(WILLNEED) |
| `L4_EVICT_META` | 0 | 1=驱逐 graph/BFS 页缓存 |
| `FINE_FADVISE` | 0 | 1=精排后驱逐页（512MB 有害） |

### 多线程 / 调试

| 变量 | 说明 |
|------|------|
| `NUM_THREADS` | >0=并发线程数 |
| `PROFILE_TS` | 1=两阶段计时 |
| `PROFILE_FINE` | 1=精排细粒度计时 |

---

## 8. 已知限制

1. **io_uring 非线程安全**：多线程必须 `FINE_PREAD=1`
2. **vecblocks 与 route 必须配套**：混用不同版本导致 offset 错误
3. **blocks 和 vecblocks 的 block_id 不一致**：各有独立 route 表
4. **cgroup memory.file ≠ page cache 总量**：首次读入在 cgroup 外时不计入
5. **WILLNEED 在 I/O 量主导场景无效**：DEEP10M 瓶颈是 majfault 总量

---

## 9. 优化历史与未来方向

### 已完成

| 里程碑 | 技术 | 效果 |
|--------|------|------|
| P0: CSR 压缩 | delta+varint | 1.8x 压缩，RSS 337→269MB |
| P0.5: 双路由表修复 | vec_route_table 分离 | 修复 block_id 不一致 bug |
| P1: 图裁剪试验 | MRNG R_max | 负结果（1M 无净收益） |
| P2: DEEP10M | VisitedList + PQ + flat_vec | 95.15% recall, 2340 QPS |
| flat_vec_cache | fine rerank 命中检查 | 7.5x@256MB |
| WILLNEED | fadvise readahead | 17.7x@256MB, 无回归@512MB |

### 未来

| 阶段 | 目标 |
|------|------|
| P3 | CSR 上磁盘（100M 必需，4.7GB 装不进内存） |
| P4 | 分级存储 + 增量插入 + 多租户 |
| P5 | 硬件亲和（NUMA/SPDK/GPU/PMEM） |
