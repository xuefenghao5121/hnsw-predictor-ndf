# Evidence: D1 - flat_vec_cache Hit Rate Diagnosis

> 日期: 2026-08-05
> 协议: [[CON-SLA-014]]
> 二进制: poc/l4-cache-mgmt/build/benchmark_l4 (当前 Trunk + FV 计数器)

## 结果

| 配置 | FVC slots | 覆盖率 | FV_hit | FV_miss | 命中率 | 总候选 |
|------|-----------|--------|--------|---------|--------|--------|
| 256MB FVC=64 1T | 130,055 | 13.0% | 18,290 | 21,710 | **45.7%** | 40,000 |
| 256MB FVC=64 16T | 130,055 | 13.0% | 18,272 | 21,728 | **45.7%** | 40,000 |
| 512MB FVC=160 1T | 325,139 | 32.5% | 19,755 | 20,245 | **49.4%** | 40,000 |
| 512MB FVC=160 16T | 325,139 | 32.5% | 19,644 | 20,356 | **49.1%** | 40,000 |

## 分析

### 1. 命中率只有 45-49%

超过一半的 FineRerank 候选仍需 pread 读磁盘。

### 2. 覆盖率 vs 命中率（边际递减）

| FVC | slots | 覆盖率 | 命中率 | 边际增益 |
|-----|-------|--------|--------|---------|
| 64MB | 130K | 13.0% | 45.7% | baseline |
| 160MB | 325K | 32.5% | 49.4% | +3.7pp (+2.5x slots) |

slots 翻 2.5x 只提升 3.7pp。说明热向量已基本被 64MB 覆盖，剩余 miss 是长尾。

### 3. miss 的候选量 ≈ 20K

200 queries × ~100 miss/query = 20K pread。每次 pread 4KB。
总 I/O = 20K × 4KB = 80MB。
256MB cgroup page cache ≈ 60MB -> 多数 pread 需要从磁盘读。

### 4. 命中率与线程数无关

45.7% @1T = 45.7% @16T。FVC 是 per-query 的，不随并发变化。

## 优化空间

### H1 否定: 命中率不能通过增大 FVC 显著提升

FVC=160 仅比 FVC=64 多 3.7pp。需要其他策略。

### 可能的方向

1. **提高 FVC 命中率**: 改进 slot 替换策略（当前 hash-based 无冲突检测）
   - 但 130K slots 已覆盖 13% 节点命中 45.7%，效率已不错
   
2. **减少 FineRerank 候选数**: REFINE_EF 降低（已测试，EF=100 最优）
   - 不能减，减了 recall 掉

3. **加速 miss 路径**: pread 本身已由 WILLNEED_BG 优化
   - 剩余 I/O 是不可避免的

4. **BlockCache 复用**: FineRerank miss 的向量在 64KB block 中，
   一个 block 包含 ~128 向量，一次读入可服务多个候选
   - 当前 pread 是 4KB 页粒度，不是 block 粒度

## 结论

flat_vec_cache 命中率 45-49%，已接近 slot-based 架构上限。
增大 FVC 边际递减明显。后续优化应聚焦 miss 路径（pread / page cache）。
