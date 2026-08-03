# VER-039 验收报告: SIFT1M 严格 cgroup 隔离基线

> 日期: 2026-08-03
> 协议: [[CON-SLA-014]] 严格 cgroup 隔离测试协议
> 关联: [[VER-039]], [[CHR-006]], [[CON-SLA-011]], [[DEC-065]], [[DEC-066]]
> 数据集: SIFT1M (128D, 1M 向量)
> 查询数: 200 (sift1m_query200.fvecs)
> cgroup: 512MB
> drop_caches: 是 (每组测试前 `sync && echo 3 > /proc/sys/vm/drop_caches`)

## 测试环境

- 机器: huawei-ThinkCentre-M960t
- OS: Linux 7.0.0-28-generic (x64)
- cgroup v2, memory_recursiveprot
- NVMe: YMTC YMSS2CB08D25MC (消费级)
- 编译: g++ -O3 -std=c++17 -march=native

## 测试结果

### 核心性能

| 模式 | 线程 | Recall | QPS | Mean (ms) | P50 (ms) | P95 (ms) | RSS (MB) |
|------|------|--------|-----|-----------|----------|----------|----------|
| Buffered | 1T | 98.35% | **22.9** | 43.74 | 46.14 | 62.25 | 235 |
| Buffered | 4T | 98.35% | **18.4** | 54.48 | 54.48 | 54.48 | 416 |
| O_DIRECT | 1T | 98.35% | **22.8** | 43.84 | 45.79 | 60.84 | 235 |
| O_DIRECT | 4T | 98.35% | **19.5** | 51.23 | 51.23 | 51.23 | 426 |

### cgroup 内存统计

| 指标 | Buffered 1T | Buffered 4T | O_DIRECT 1T | O_DIRECT 4T |
|------|-------------|-------------|-------------|-------------|
| memory.peak | 512MB (满) | 512MB (满) | 512MB (满) | 512MB (满) |
| `max` events | 1523 | 3558 | 5084 | 7141 |
| `oom` events | 0 ✅ | 0 ✅ | 0 ✅ | 0 ✅ |
| peak anon (MB) | 246 | 392 | - | - |
| peak file (MB) | 400 | 441 | - | - |
| peak total (MB) | 512 | 512 | - | - |
| workingset_refault_file | 0 | 9 | 82 | 147 |
| pgmajfault | 5 | 27 | 73 | 112 |
| BlockCache hit% | 71.9% | 67.0% | 71.9% | 67.0% |

### 协议合规性

| 检查项 | 状态 |
|--------|------|
| drop_caches 执行 | ✅ 每组测试前执行 |
| cgroup memory.max = 512MB | ✅ |
| oom = 0 | ✅ 所有组 |
| memory.peak ≤ memory.max | ✅ (等于，未超) |
| page cache 在 cgroup 内记账 | ✅ (peak file 400MB, 非零) |

## 与旧基线（白嫖）对比

| 模式 | 线程 | 旧基线 (白嫖) | 严格基线 | 下降倍数 | 根因 |
|------|------|---------------|----------|----------|------|
| Buffered | 1T | ~2300 QPS | 22.9 QPS | **100x** | page cache 被内核回收，每次查询重新读盘 |
| Buffered | 4T | ~5800 QPS | 18.4 QPS | **315x** | 4T 竞争 512MB，anon 涨至 392MB，file 空间更少 |
| O_DIRECT | 1T | ~130 QPS | 22.8 QPS | **5.7x** | graph/PQ/BFS 等元数据文件的 page cache 也被回收 |
| O_DIRECT | 4T | ~502 QPS | 19.5 QPS | **25.7x** | 同上 + 4T 内存竞争 |

## 关键发现

1. **page cache 白嫖是之前性能的主要来源**：旧基线 2300 QPS 中绝大部分来自 root cgroup 预热的 ~450MB vecblocks page cache。严格隔离后 cgroup 撞满 512MB 限制，内核疯狂回收（max events 1523-7141 次），每次查询都重新读盘。

2. **O_DIRECT 也受影响**：O_DIRECT 只绕过 vecblocks 的 page cache，但 graph（587MB）、PQ codes（31MB）等元数据文件仍是 buffered I/O，严格隔离下其 page cache 也被记账并回收。

3. **4T 比 1T 更差**：4 线程竞争 512MB 预算，peak anon 从 246MB 涨到 392MB（VisitedList × 4），留给 page cache 的空间更少。

4. **512MB 在严格隔离下不足以有效运行 SIFT1M**：内存预算被 RSS 和 page cache 瓜分，内核持续回收，性能地板极低。

## 结论

- [[CON-SLA-014]] 为现行最合理测法；本报告数字为后续 POC **对齐基线**（非白嫖 must 复活）
- 旧 SLA QPS（Buffered ≥2000 等）经 [[DEC-066]] 废止
- [[CHR-006]] must：Recall / RSS(1T≤300,4T≤450) / peak / oom；QPS 为观测锚点
- 需继续：DEEP10M 严格隔离基线；pipe_ring_ POC 以本基线为 R0
