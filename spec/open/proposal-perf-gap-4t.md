# Proposal: SIFT1M 4T 性能差距优化

> track: poc
> 日期: 2026-08-05
> Status: Pending
> 关联: [[CHR-006]]、[[CON-SLA-014]]、[[CON-HONEST-002]]、[[CON-POC-001]]、[[BEH-001]]、[[BEH-007]]
> 依赖主题: `poc/multi-thread-scaling/`（平级新 topic，`depends_on_topics`）

## 1. 问题陈述

### 临时基线 (SIFT1M 4T, CON-SLA-014)

| 指标 | DiskHNSW (512MB cgroup) | hnswlib (unlimited) | 差距 |
|------|------------------------|--------------------|----|
| QPS | 9,657 | 18,496 | 52% |
| Recall@10 | 95.80% | 98.30% | -2.5pp |
| P99 latency | 0.89ms | 0.37ms | 2.4x |
| 内存占用 | 512MB (cgroup: anon~202MB + file~308MB) | 732MB (RSS: 全 anonymous) | 70% |

> **内存对比口径**: DiskHNSW 使用 cgroup memory.max=512MB（含 anon + page cache），
> hnswlib 使用 RSS（全 anonymous，无 cgroup 限制）。之前 RSS-only 对比 (202/732=28%)
> 严重低估了 DiskHNSW 的实际内存占用。

**目标**: 在 512MB cgroup 约束下，缩小与 hnswlib unlimited 4T 的 QPS 和 recall 差距。

### 差距来源（从 multi-thread-scaling POC 继承）

| 来源 | QPS 影响 | Recall 影响 | 可优化? |
|------|---------|------------|--------|
| PQ 近似 vs 精确距离 | 基线 | -2.5pp | ✅ PQ 质量/编码优化 |
| FineRerank 磁盘 I/O | 主要 QPS 瓶颈 | - | ✅ cache/I/O 优化 |
| 内存约束 (512MB vs 732MB) | page cache 受限 | - | ✅ cache 策略 |
| VisitedList memset | 4T ~5% | - | ✅ 池化 |

## 2. 探索方向

### 方向 1: flat_vec_cache 调优 (低复杂度, 快速验证)

当前 FLAT_VEC_MB=64 装载 65K 上层向量。调大可能提高 cache 命中率，减少 I/O。

- 测试: FLAT_VEC_MB = 64/96/128/160/192
- 约束: 512MB cgroup 内 anon + file 不超限
- 预期: +5-15% QPS（减少 FineRerank pread 次数）

### 方向 2: PQ 质量优化 (中复杂度)

当前 M=32, recall=95.80%。提升 PQ 编码质量可同时提升 recall 和 QPS（减少 FineRerank 候选数）。

- 测试: M=48/M=64, OPQ 旋转
- 约束: PQ codes 内存 = N*M bytes, M=64 -> 64MB (当前 32MB)
- 预期: recall +1-2pp, 可能 QPS +10%（更少 FineRerank 候选）

### 方向 3: FineRerank I/O 优化 (中高复杂度)

当前 FineRerank 按 4KB 页 pread。优化方向：
- 候选页去重 + 批量 pread（减少 syscall）
- pread 合并（相邻页合并为一次 8KB/16KB 读）
- flat_vec_cache 命中率提升（减少 pread 总量）

### 方向 4: VisitedList 池化 (中复杂度)

4T 下 memset 占 5.38%。线程局部 VisitedList 池可复用，减少 memset 和分配开销。

### 方向 5: ef/refine_ef 调优 (低复杂度)

当前 ef=100, REFINE_EF=100。降低 FineRerank 候选数可减少 I/O，但可能影响 recall。

## 3. 不做的事

- 不改 Trunk `src/` 生产代码
- 不写 stable must SLA
- 不改 512MB cgroup 约束
- 不改搜索算法核心逻辑（HNSW 图遍历）

## 4. 验证协议

所有测试对齐 [[CON-SLA-014]]：drop_caches + 512MB cgroup + 4T。
对比目标：hnswlib unlimited 4T = 18496 QPS / 98.30% recall。

## 5. 晋升条件

若某方向验证有效（QPS 提升 >5% 或 recall 提升 >0.5pp），另开 promote 提案，
引用本主题 TOPIC.md，走 [[BEH-019]] 干净合入。
