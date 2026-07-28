# Verification — 测试用例与断言条件

## 测试套件结构 {#OBS-VER-001}
<!-- ndf: kind=verif level=must layer=L3 status=stable since=0.1 source=observed -->

| 测试 | 文件 | 覆盖范围 | 断言类型 |
|------|------|---------|---------|
| BlockCache 单元测试 | `test_block_cache.cpp` | 加载、命中、淘汰、数据正确性、统计 | ASSERT_EQ/ASSERT_TRUE |
| DiskHNSW 集成测试 | `test_disk_hnsw.cpp` | recall 一致性、搜索正确性、可插拔策略 | recall 比较 |
| PQ 搜索质量 | `test_pq_search_quality.cpp` | PQ ADC 距离 vs 真实 L2、recall@10 | 手动检查输出 |

## test_block_cache 断言提取 {#OBS-VER-002}
<!-- ndf: kind=verif level=must layer=L3 status=stable since=0.1 source=observed verifies=OBS-BEH-009,OBS-BEH-010 -->

### test_basic_loading (`test_block_cache.cpp:91-106`)

- [ ] BlockCache 构造后，`getNumBlocks()` MUST == 3（1K 节点测试数据）
- [ ] `getNumNodes()` MUST == 1000
- [ ] `getBlockSize()` MUST == 256 * 1024
- [ ] `getCacheSlots()` MUST == 64
- [ ] `getNumCachedBlocks()` MUST == 0（初始无缓存）

### test_cache_hit_miss (`test_block_cache.cpp:108-137`)

- [ ] 首次 `getNodeVector(0)` MUST 返回非 nullptr
- [ ] 首次访问后 `total_accesses == 1`, `cache_misses == 1`, `cache_hits == 0`
- [ ] 第二次 `getNodeVector(0)` MUST 返回与首次相同的指针
- [ ] 第二次访问后 `total_accesses == 2`, `cache_misses == 1`, `cache_hits == 1`

### test_lru_eviction (`test_block_cache.cpp:139-177`)

- [ ] cache_slots=1 时，访问不同 block 的节点 MUST 触发淘汰
- [ ] 访问 node 0 (block 0) 后 `num_cached == 1`, `misses == 1`, `evictions == 0`
- [ ] node 0 和 node 500 MUST 在不同 block 中
- [ ] 访问 node 500 后 `misses == 2`, `evictions == 1`
- [ ] 再次访问 node 0 后 `evictions == 2`

### test_data_correctness (`test_block_cache.cpp:179-200+`)

- [ ] BlockCache 返回的向量数据 MUST 与 graph.bin 原始数据一致
- [ ] BlockCache 返回的邻居列表 MUST 与 graph.bin 原始数据一致
- [ ] 对所有节点 (0..N-1) 验证上述一致性

## test_disk_hnsw 断言提取 {#OBS-VER-003}
<!-- ndf: kind=verif level=must layer=L3 status=stable since=0.1 source=observed verifies=OBS-BEH-001,OBS-BEH-003 -->

### recall 一致性 (`test_disk_hnsw.cpp`)

从测试代码逻辑反向提取：
- [ ] DiskHNSW 搜索结果 SHOULD 与 hnswlib 全内存搜索结果有高 recall (≥95%)
- [ ] `computeRecall()` MUST 使用 set intersection 计算 recall@k (`test_disk_hnsw.cpp:36-54`)
- [ ] Ground truth MUST 通过暴力 L2 搜索生成 (`test_disk_hnsw.cpp:57-88`)
- [ ] 支持 3 种 IO 模式：cached / direct (O_DIRECT) / simulated (模拟延迟)
- [ ] 支持 3 种替换策略：lru / lfu / lru-k
- [ ] 支持 2 种布局策略：bfs / random

### 可插拔策略测试 (`test_disk_hnsw.cpp:98-113`)

- [ ] `--io-mode=cached|direct|simulated` MUST 正确配置 IOConfig
- [ ] `--layout=bfs|random` MUST 创建对应的 LayoutProvider
- [ ] `--policy=lru|lfu|lru-k` MUST 创建对应的 ReplacementPolicy

## benchmark 正确性条件 {#OBS-VER-004}
<!-- ndf: kind=verif level=must layer=L3 status=stable since=0.1 source=observed verifies=OBS-BEH-013 -->

### recall 计算 (`benchmark_diskhnsw.cpp`)

- [ ] GT 文件 MUST 有 8B header (n_queries:u32 + K:u32)
- [ ] 搜索结果的 label (uint64) MUST 与 GT 的 neighbor id 比较
- [ ] Recall = hits / (num_query * k)
- [ ] benchmark 运行时的 K MUST == GT 生成时的 K（否则 offset 错位）

### RSS 测量 (`benchmark_diskhnsw.cpp:25-36`)

- [ ] RSS MUST 从 `/proc/self/status` 的 VmRSS 字段读取
- [ ] 单位 MUST 为 MB (kB / 1024)

### 公平对比条件 (`compare_benchmark.sh`)

- [ ] DiskHNSW 和 hnswlib MUST 使用相同的 query / GT / k / ef
- [ ] DiskHNSW MUST 在 cgroup MemoryMax 限制下运行
- [ ] hnswlib MUST 放开 cgroup 限制
- [ ] 两者 MUST 经过相同的 warmup（CPU 升频 + page cache 预热 + 全 query 预跑）
- [ ] MUST 多轮取峰值 QPS（排除调频抖动）

## PQ 质量自检 {#OBS-VER-005}
<!-- ndf: kind=verif level=should layer=L3 status=stable since=0.1 source=observed verifies=OBS-BEH-005 -->

### train_pq.py 自检 (`train_pq.py:122-138`)

- [ ] ADC top-10 overlap SHOULD > 90%（SIFT+M=32）
- [ ] 重建 MSE SHOULD 被打印（相对能量百分比）
- [ ] PQ codebook MUST 保存为 `M*256*(dim/M)` floats

### test_pq_search_quality 检查 (`test_pq_search_quality.cpp:56-103`)

- [ ] 对前 5 个 query，打印 PQ 距离 vs 真实 L2 距离
- [ ] 计算 recall@10 并输出
- [ ] GT 的 true_dist 和 pq_dist MUST 同时打印用于人工对比
